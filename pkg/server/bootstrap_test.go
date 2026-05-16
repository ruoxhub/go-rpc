package server

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/server/api"
	"github.com/mrh30000/go-rpc/pkg/server/client"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
	"github.com/mrh30000/go-rpc/pkg/server/websocket"
)

func TestRegisterRoutesChatCompletionsAndV1NoRoute(t *testing.T) {
	gin.SetMode(gin.TestMode)

	timeoutMgr := forwarder.NewTimeoutManager(nil)
	clientManager := client.NewClientManager()
	wsHandler := websocket.NewHandler(clientManager, timeoutMgr, nil, nil)
	defer wsHandler.Shutdown()

	httpServer := api.NewHTTPServer(&api.Config{
		Host:         "127.0.0.1",
		Port:         0,
		ReadTimeout:  time.Second,
		WriteTimeout: 0,
		Mode:         gin.TestMode,
	})

	s := &Server{
		httpServer:     httpServer,
		clientManager:  clientManager,
		wsHandler:      wsHandler,
		timeoutManager: timeoutMgr,
		apiHandler:     api.NewAPIHandler(clientManager, wsHandler, timeoutMgr, nil, nil),
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
