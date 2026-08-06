package main

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	gorillawebsocket "github.com/gorilla/websocket"
	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/pkg/client"
	pkgconfig "github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/handler"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/websocket"
)

func TestRegisterRoutesChatCompletionsAndV1NoRoute(t *testing.T) {
	gin.SetMode(gin.TestMode)

	timeoutMgr := forwarder.NewTimeoutManager(nil)
	clientManager := client.NewClientManager()
	wsHandler := websocket.NewHandler(clientManager, timeoutMgr, nil, nil, nil)
	defer wsHandler.Shutdown()

	httpServer := handler.NewHTTPServer(&handler.HTTPConfig{
		Host:         "127.0.0.1",
		Port:         0,
		ReadTimeout:  time.Second,
		WriteTimeout: 0,
		Mode:         gin.TestMode,
	})

	s := &Server{
		serverConfig:   &config.ServerConfig{DisableWebAdmin: true, DisableDatabase: true},
		httpServer:     httpServer,
		clientManager:  clientManager,
		wsHandler:      wsHandler,
		timeoutManager: timeoutMgr,
		apiHandler:     handler.NewAPIHandler(clientManager, wsHandler, timeoutMgr, nil, nil, nil, nil, nil),
	}
	s.registerRoutes()

	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions?group=g1", strings.NewReader(`{`))
	req.Header.Set("Content-Type", "application/json")
	httpServer.Engine().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("chat route status = %d, want 400", w.Code)
	}

	w = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/v1/unknown", nil)
	httpServer.Engine().ServeHTTP(w, req)
	if w.Code != http.StatusNotFound {
		t.Fatalf("v1 noroute status = %d, want 404", w.Code)
	}
	if !strings.Contains(w.Body.String(), "Not found") {
		t.Fatalf("v1 noroute body = %s", w.Body.String())
	}
}

func TestNewHTTPConfigPreservesGlobalWriteTimeout(t *testing.T) {
	s := NewServer(&Config{Host: "127.0.0.1", Port: 5612})
	defer s.timeoutManager.Shutdown()
	cfg := s.newHTTPConfig(gin.TestMode)

	if cfg.WriteTimeout != 30*time.Second {
		t.Fatalf("WriteTimeout = %v, want 30s", cfg.WriteTimeout)
	}
	if cfg.ReadTimeout != 30*time.Second {
		t.Fatalf("ReadTimeout = %v, want 30s", cfg.ReadTimeout)
	}
}

func TestShutdown_NilDatabaseNoPanic(t *testing.T) {
	s := &Server{}
	s.Shutdown()
}

func TestAuthorizeRegisterAccess_DBlessAllowsAnonymousRegistration(t *testing.T) {
	gin.SetMode(gin.TestMode)
	s := &Server{serverConfig: &config.ServerConfig{DisableDatabase: true}}
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/register?group=kalodata&clientId=test", nil)
	if !s.authorizeRegisterAccess(c, "kalodata") {
		t.Fatalf("authorizeRegisterAccess() = false in DB-less mode; status=%d body=%s", w.Code, w.Body.String())
	}
	if w.Code == http.StatusServiceUnavailable {
		t.Fatalf("DB-less registration returned 503: %s", w.Body.String())
	}
}

func TestAuthorizeRegisterAccess_DatabaseModeWithoutDependenciesFailsClosed(t *testing.T) {
	gin.SetMode(gin.TestMode)
	s := &Server{serverConfig: &config.ServerConfig{DisableDatabase: false}}
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/register?group=kalodata&clientId=test", nil)
	if s.authorizeRegisterAccess(c, "kalodata") {
		t.Fatal("authorizeRegisterAccess() = true without database authorization dependencies")
	}
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want %d; body=%s", w.Code, http.StatusServiceUnavailable, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "group access verification unavailable") {
		t.Fatalf("unexpected response body: %s", w.Body.String())
	}
}

type registerTokenLookupFunc func(token string) (*model.UserInfo, error)

func (f registerTokenLookupFunc) FindByToken(token string) (*model.UserInfo, error) {
	return f(token)
}

type registerGroupRepositoryStub struct {
	repository.GroupRepository
}

func newRegisterTestServer(t *testing.T, disableDatabase bool) *Server {
	t.Helper()

	timeoutMgr := forwarder.NewTimeoutManager(nil)
	clientManager := client.NewClientManager()
	wsHandler := websocket.NewHandler(clientManager, timeoutMgr, nil, nil, nil)
	wsCtx, wsCancel := context.WithCancel(context.Background())
	httpServer := handler.NewHTTPServer(&handler.HTTPConfig{
		Host:         "127.0.0.1",
		Port:         0,
		ReadTimeout:  time.Second,
		WriteTimeout: 0,
		Mode:         gin.TestMode,
	})

	t.Cleanup(func() {
		wsCancel()
		wsHandler.Shutdown()
		timeoutMgr.Shutdown()
	})

	return &Server{
		serverConfig:   &config.ServerConfig{DisableWebAdmin: true, DisableDatabase: disableDatabase},
		httpServer:     httpServer,
		clientManager:  clientManager,
		wsHandler:      wsHandler,
		timeoutManager: timeoutMgr,
		apiHandler:     handler.NewAPIHandler(clientManager, wsHandler, timeoutMgr, nil, nil, nil, nil, nil),
		wsCtx:          wsCtx,
		wsCancel:       wsCancel,
	}
}

func newRegisterAuthMiddleware(
	userLookup middleware.TokenUserLookup,
	groupLookup middleware.GroupConfigLookup,
) *middleware.AuthMiddleware {
	return middleware.NewAuthMiddleware(
		userLookup,
		groupLookup,
		middleware.DefaultTokenCache(),
		middleware.DefaultGroupCache(),
		nil,
	)
}

func TestBusinessRegisterRoute_DBlessValidationAndUpgrade(t *testing.T) {
	gin.SetMode(gin.TestMode)
	s := newRegisterTestServer(t, true)
	s.registerRoutes()

	for _, tc := range []struct {
		name string
		url  string
	}{
		{name: "missing group", url: "/business/register?clientId=device-1"},
		{name: "missing clientId", url: "/business/register?group=anonymous-group"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			w := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, tc.url, nil)
			s.httpServer.Engine().ServeHTTP(w, req)

			if w.Code != http.StatusBadRequest {
				t.Fatalf("status = %d, want %d; body=%s", w.Code, http.StatusBadRequest, w.Body.String())
			}
			if !strings.Contains(w.Body.String(), "group and clientId parameters required") {
				t.Fatalf("unexpected response body: %s", w.Body.String())
			}
		})
	}

	httpTestServer := httptest.NewServer(s.httpServer.Engine())
	defer httpTestServer.Close()
	wsURL := "ws" + strings.TrimPrefix(httpTestServer.URL, "http") +
		"/business/register?group=anonymous-group&clientId=device-1"
	conn, response, err := gorillawebsocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		status := 0
		if response != nil {
			status = response.StatusCode
		}
		t.Fatalf("WebSocket dial failed with status %d: %v", status, err)
	}
	defer conn.Close()
	if response.StatusCode != http.StatusSwitchingProtocols {
		t.Fatalf("status = %d, want %d", response.StatusCode, http.StatusSwitchingProtocols)
	}
}

func TestAuthorizeRegisterAccess_DatabaseModeMissingDependencyMatrix(t *testing.T) {
	gin.SetMode(gin.TestMode)
	authMW := newRegisterAuthMiddleware(
		registerTokenLookupFunc(func(string) (*model.UserInfo, error) { return nil, nil }),
		func(string) (*model.GroupConfig, error) { return nil, nil },
	)
	nonNilGroupRepo := &registerGroupRepositoryStub{}

	for _, tc := range []struct {
		name      string
		groupRepo repository.GroupRepository
		authMW    *middleware.AuthMiddleware
	}{
		{name: "only groupRepo missing", authMW: authMW},
		{name: "only authMW missing", groupRepo: nonNilGroupRepo},
	} {
		t.Run(tc.name, func(t *testing.T) {
			s := &Server{
				serverConfig: &config.ServerConfig{DisableDatabase: false},
				groupRepo:    tc.groupRepo,
				authMW:       tc.authMW,
			}
			w := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(w)
			c.Request = httptest.NewRequest(http.MethodGet, "/business/register?group=registered&clientId=device-1", nil)

			if s.authorizeRegisterAccess(c, "registered") {
				t.Fatal("authorizeRegisterAccess() = true with a missing authorization dependency")
			}
			if w.Code != http.StatusServiceUnavailable {
				t.Fatalf("status = %d, want %d; body=%s", w.Code, http.StatusServiceUnavailable, w.Body.String())
			}
			if !strings.Contains(w.Body.String(), "group access verification unavailable") {
				t.Fatalf("unexpected response body: %s", w.Body.String())
			}
		})
	}
}

func TestAuthorizeRegisterAccess_DatabaseModeAuthorizationMatrix(t *testing.T) {
	gin.SetMode(gin.TestMode)
	middleware.InvalidateAllGroups()
	middleware.InvalidateAllTokens()
	t.Cleanup(func() {
		middleware.InvalidateAllGroups()
		middleware.InvalidateAllTokens()
	})

	for _, tc := range []struct {
		name        string
		groupName   string
		groupOwner  string
		token       string
		user        *model.UserInfo
		wantAllowed bool
		wantStatus  int
		wantBody    string
	}{
		{
			name:        "anonymous group allowed by default",
			groupName:   "anonymous-default",
			wantAllowed: true,
			wantStatus:  http.StatusOK,
		},
		{
			name:       "registered group missing token denied",
			groupName:  "registered-missing-token",
			groupOwner: "owner",
			wantStatus: http.StatusUnauthorized,
			wantBody:   "registered group requires a valid rpc token",
		},
		{
			name:       "registered group invalid token denied",
			groupName:  "registered-invalid-token",
			groupOwner: "owner",
			token:      "invalid-token",
			wantStatus: http.StatusUnauthorized,
			wantBody:   "registered group requires a valid rpc token",
		},
		{
			name:        "owning user allowed",
			groupName:   "registered-owner",
			groupOwner:  "owner",
			token:       "owner-token",
			user:        &model.UserInfo{UserName: "owner"},
			wantAllowed: true,
			wantStatus:  http.StatusOK,
		},
		{
			name:        "admin allowed",
			groupName:   "registered-admin",
			groupOwner:  "owner",
			token:       "admin-token",
			user:        &model.UserInfo{UserName: "admin", IsAdmin: true},
			wantAllowed: true,
			wantStatus:  http.StatusOK,
		},
		{
			name:       "non-owner denied",
			groupName:  "registered-non-owner",
			groupOwner: "owner",
			token:      "non-owner-token",
			user:       &model.UserInfo{UserName: "other"},
			wantStatus: http.StatusForbidden,
			wantBody:   "no access to registered group",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var group *model.GroupConfig
			if tc.groupOwner != "" {
				group = &model.GroupConfig{GroupName: tc.groupName, UserName: tc.groupOwner}
			}
			authMW := newRegisterAuthMiddleware(
				registerTokenLookupFunc(func(token string) (*model.UserInfo, error) {
					if token == tc.token && tc.user != nil {
						return tc.user, nil
					}
					return nil, errors.New("token not found")
				}),
				func(groupName string) (*model.GroupConfig, error) {
					if groupName != tc.groupName {
						t.Fatalf("group lookup name = %q, want %q", groupName, tc.groupName)
					}
					return group, nil
				},
			)
			s := &Server{
				serverConfig:  &config.ServerConfig{DisableDatabase: false},
				configService: pkgconfig.NewService(),
				groupRepo:     &registerGroupRepositoryStub{},
				authMW:        authMW,
			}
			w := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(w)
			c.Request = httptest.NewRequest(http.MethodGet, "/business/register?group="+tc.groupName+"&clientId=device-1", nil)
			if tc.token != "" {
				c.Request.Header.Set("Authorization", "Bearer "+tc.token)
			}

			if got := s.authorizeRegisterAccess(c, tc.groupName); got != tc.wantAllowed {
				t.Fatalf("authorizeRegisterAccess() = %v, want %v; status=%d body=%s", got, tc.wantAllowed, w.Code, w.Body.String())
			}
			if w.Code != tc.wantStatus {
				t.Fatalf("status = %d, want %d; body=%s", w.Code, tc.wantStatus, w.Body.String())
			}
			if tc.wantBody != "" && !strings.Contains(w.Body.String(), tc.wantBody) {
				t.Fatalf("response body = %s, want substring %q", w.Body.String(), tc.wantBody)
			}
		})
	}
}
