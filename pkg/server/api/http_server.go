package api

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
)

// Config holds HTTP server configuration
type Config struct {
	Host         string
	Port         int
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
}

// DefaultConfig returns default HTTP configuration
func DefaultConfig() *Config {
	return &Config{
		Host:         "0.0.0.0",
		Port:         5612,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
	}
}

// HTTPServer wraps net/http.Server with WebSocket support
type HTTPServer struct {
	server     *http.Server
	router     *http.ServeMux
	wsUpgrader *websocket.Upgrader
	addr       string
}

// NewHTTPServer creates a new HTTPServer
func NewHTTPServer(cfg *Config) *HTTPServer {
	s := &HTTPServer{
		router: http.NewServeMux(),
		wsUpgrader: &websocket.Upgrader{
			ReadBufferSize:  1024,
			WriteBufferSize: 1024,
			CheckOrigin:     func(r *http.Request) bool { return true },
		},
	}

	s.server = &http.Server{
		Addr:         fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
		Handler:      s.router,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
	}

	return s
}

// Start starts the HTTP server
func (s *HTTPServer) Start() error {
	ln, err := net.Listen("tcp", s.server.Addr)
	if err != nil {
		return err
	}
	s.addr = ln.Addr().String()

	go func() {
		_ = s.server.Serve(ln)
	}()

	return nil
}

// Addr returns the server address
func (s *HTTPServer) Addr() string {
	return s.addr
}

// Shutdown gracefully shuts down the server
func (s *HTTPServer) Shutdown() error {
	return s.server.Shutdown(context.Background())
}

// RegisterHandler registers an HTTP handler
func (s *HTTPServer) RegisterHandler(pattern string, handler http.HandlerFunc) {
	s.router.HandleFunc(pattern, handler)
}

// WSUpgrader returns the WebSocket upgrader
func (s *HTTPServer) WSUpgrader() *websocket.Upgrader {
	return s.wsUpgrader
}

// Server returns the underlying http.Server
func (s *HTTPServer) Server() *http.Server {
	return s.server
}
