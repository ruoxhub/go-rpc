package api

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
)

// Config holds HTTP server configuration
type Config struct {
	Host         string
	Port         int
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	Mode         string // "debug", "release", "test"
	LocalDebug   bool   // allow all origins in local debug mode
}

// DefaultConfig returns default HTTP configuration
func DefaultConfig() *Config {
	return &Config{
		Host:         "0.0.0.0",
		Port:         5612,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		Mode:         gin.ReleaseMode,
	}
}

// HTTPServer wraps gin.Engine with WebSocket support
type HTTPServer struct {
	engine     *gin.Engine
	server     *http.Server
	wsUpgrader *websocket.Upgrader
	addr       string
}

// NewHTTPServer creates a new HTTPServer with gin
func NewHTTPServer(cfg *Config) *HTTPServer {
	// Set gin mode
	gin.SetMode(cfg.Mode)

	engine := gin.New()
	engine.Use(gin.Recovery())

	s := &HTTPServer{
		engine: engine,
		wsUpgrader: &websocket.Upgrader{
			ReadBufferSize:  1024,
			WriteBufferSize: 1024,
			CheckOrigin:     func(r *http.Request) bool { return true },
		},
	}

	s.server = &http.Server{
		Addr:         fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
		Handler:      engine,
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

// RegisterHandler registers an HTTP handler (for backward compatibility)
func (s *HTTPServer) RegisterHandler(pattern string, handler http.HandlerFunc) {
	s.engine.Handle("GET", pattern, gin.WrapF(handler))
}

// RegisterRoute registers a route with gin handler
func (s *HTTPServer) RegisterRoute(method, path string, handler gin.HandlerFunc) {
	s.engine.Handle(method, path, handler)
}

// GET registers a GET route
func (s *HTTPServer) GET(path string, handler gin.HandlerFunc) {
	s.engine.GET(path, handler)
}

// POST registers a POST route
func (s *HTTPServer) POST(path string, handler gin.HandlerFunc) {
	s.engine.POST(path, handler)
}

// Any registers a route that handles all HTTP methods
func (s *HTTPServer) Any(path string, handler gin.HandlerFunc) {
	s.engine.Any(path, handler)
}

// Use registers middleware
func (s *HTTPServer) Use(middleware ...gin.HandlerFunc) {
	s.engine.Use(middleware...)
}

// Group creates a new route group
func (s *HTTPServer) Group(relativePath string, handlers ...gin.HandlerFunc) *gin.RouterGroup {
	return s.engine.Group(relativePath, handlers...)
}

// Engine returns the underlying gin.Engine
func (s *HTTPServer) Engine() *gin.Engine {
	return s.engine
}

// Server returns the underlying http.Server
func (s *HTTPServer) Server() *http.Server {
	return s.server
}

// WSUpgrader returns the WebSocket upgrader
func (s *HTTPServer) WSUpgrader() *websocket.Upgrader {
	return s.wsUpgrader
}

func sameOriginOrNoOrigin(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" {
		return true
	}

	if !strings.HasPrefix(origin, "http://") && !strings.HasPrefix(origin, "https://") {
		return false
	}

	originHost := strings.TrimPrefix(strings.TrimPrefix(origin, "http://"), "https://")
	// 去除端口后再比较，允许同域名不同端口的 WebSocket 连接
	if idx := strings.LastIndex(originHost, ":"); idx != -1 {
		originHost = originHost[:idx]
	}
	reqHost := r.Host
	if idx := strings.LastIndex(reqHost, ":"); idx != -1 {
		reqHost = reqHost[:idx]
	}
	return strings.EqualFold(originHost, reqHost)
}
