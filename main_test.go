package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/handler"
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
