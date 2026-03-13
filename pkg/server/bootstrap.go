// Package server implements the Sekiro server
package server

import (
	"context"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/internal/config"
	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/server/api"
	"github.com/sekiro-go/sekiro-go/pkg/server/client"
	"github.com/sekiro-go/sekiro-go/pkg/server/forwarder"
	"github.com/sekiro-go/sekiro-go/pkg/server/websocket"
)

// Config holds server configuration
type Config struct {
	Port       int
	Host       string
	Debug      bool
	LocalDebug bool
	ConfigPath string // YAML configuration file path
}

// DefaultConfig returns default configuration
func DefaultConfig() *Config {
	return &Config{
		Port:       5612,
		Host:       "0.0.0.0",
		Debug:      false,
		LocalDebug: false,
		ConfigPath: "config.yaml",
	}
}

// Server represents the Sekiro server
type Server struct {
	config         *Config
	yamlConfig     *config.Config // YAML configuration
	shutdown       chan struct{}
	clientManager  *client.ClientManager
	httpServer     *api.HTTPServer
	apiHandler     *api.APIHandler
	wsHandler      *websocket.Handler
	timeoutManager *forwarder.TimeoutManager
}

// NewServer creates a new Server
func NewServer(config *Config) *Server {
	return &Server{
		config:         config,
		shutdown:       make(chan struct{}),
		clientManager:  client.NewClientManager(),
		timeoutManager: forwarder.NewTimeoutManager(nil),
	}
}

// loadYAMLConfig loads configuration from YAML file
func (s *Server) loadYAMLConfig() error {
	// Parse command line flag for config path
	flag.StringVar(&s.config.ConfigPath, "c", "config.yaml", "指定配置文件的路径")
	flag.Parse()

	var err error
	s.yamlConfig, err = config.Load(s.config.ConfigPath)
	if err != nil {
		logger.Warningf("Failed to load YAML config: %v, using defaults", err)
		s.yamlConfig = config.DefaultConfig()
	}
	return nil
}

// applyYAMLConfig applies YAML configuration to server
func (s *Server) applyYAMLConfig() {
	if s.yamlConfig == nil {
		return
	}

	// Apply host and port if not overridden by command line
	if s.config.Host == "" {
		s.config.Host = s.yamlConfig.Host
	}
	if s.config.Port == 0 {
		s.config.Port = s.yamlConfig.Port
	}

	// Apply debug mode
	if s.yamlConfig.Mode == "debug" {
		s.config.Debug = true
	}
}

// Start starts the server
func (s *Server) Start() error {
	// Load YAML configuration
	s.loadYAMLConfig()

	// Apply YAML configuration
	s.applyYAMLConfig()

	// Initialize logger
	logger.InitLogger(s.config.Debug)

	// Initialize WebSocket handler
	s.wsHandler = websocket.NewHandler(s.clientManager, s.timeoutManager, nil)

	// Initialize API handler with WebSocket handler and timeout manager
	s.apiHandler = api.NewAPIHandler(s.clientManager, s.wsHandler, s.timeoutManager)

	// Create HTTP server with gin
	mode := gin.ReleaseMode
	if s.config.Debug {
		mode = gin.DebugMode
	}
	httpCfg := &api.Config{
		Host:         s.config.Host,
		Port:         s.config.Port,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		Mode:         mode,
	}
	s.httpServer = api.NewHTTPServer(httpCfg)

	// Apply middleware
	corsEnabled := s.yamlConfig != nil && s.yamlConfig.Cors
	routeReplaceEnabled := s.yamlConfig != nil && s.yamlConfig.RouterReplace.IsEnable
	routePrefix := ""
	if s.yamlConfig != nil {
		routePrefix = s.yamlConfig.RouterReplace.ReplaceRoute
	}

	// Register gin middleware
	s.httpServer.Use(
		ginCorsMiddleware(corsEnabled),
		ginRouteReplaceMiddleware(routeReplaceEnabled, routePrefix),
	)

	// Register routes using gin
	s.registerRoutes()

	// Create listener
	addr := fmt.Sprintf("%s:%d", s.config.Host, s.config.Port)
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to create listener: %w", err)
	}

	logger.Infof("Sekiro server starting on %s", addr)
	logger.Infof("CORS enabled: %v", corsEnabled)
	if routeReplaceEnabled {
		logger.Infof("Route prefix replacement enabled: %s", routePrefix)
	}
	logger.Info("Welcome to use Sekiro framework")

	// Start HTTP server with listener
	go func() {
		if err := s.httpServer.Server().Serve(listener); err != nil && err != http.ErrServerClosed {
			logger.Errorf("HTTP server error: %v", err)
		}
	}()

	// Wait for shutdown signal
	s.waitForShutdown()

	return nil
}

// registerRoutes registers all HTTP routes
func (s *Server) registerRoutes() {
	// Business group
	business := s.httpServer.Group("/business")
	{
		// API routes
		business.GET("/groupList", s.apiHandler.HandleGroupList)
		business.GET("/clientQueue", s.apiHandler.HandleClientQueue)
		business.Any("/invoke", s.apiHandler.HandleInvoke)

		// JS execution routes
		business.GET("/execjs", s.apiHandler.HandleExecJS)
		business.POST("/execjs", s.apiHandler.HandleExecJS)
		business.GET("/cookie", s.apiHandler.HandleGetCookie)
		business.POST("/cookie", s.apiHandler.HandleGetCookie)
		business.GET("/html", s.apiHandler.HandleGetHtml)

		// WebSocket register route
		business.GET("/register", s.handleRegister)
	}
}

// HandleRegister is a wrapper for backward compatibility
func (s *Server) handleRegister(c *gin.Context) {
	group := c.Query("group")
	clientID := c.Query("clientId")

	if group == "" || clientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "group and clientId parameters required",
		})
		return
	}

	// WebSocket upgrade
	wsConn, err := s.httpServer.WSUpgrader().Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		logger.Errorf("WebSocket upgrade error: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "WebSocket upgrade failed",
		})
		return
	}

	// Handle WebSocket connection
	go s.wsHandler.HandleConnection(context.Background(), wsConn, group, clientID)
}

// waitForShutdown waits for shutdown signal
func (s *Server) waitForShutdown() {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	select {
	case <-sigChan:
		logger.Info("Shutdown signal received")
	case <-s.shutdown:
	}

	s.Shutdown()
}

// Shutdown gracefully shuts down the server
func (s *Server) Shutdown() {
	logger.Info("Shutting down server...")

	close(s.shutdown)

	// Shutdown HTTP server
	if s.httpServer != nil {
		s.httpServer.Shutdown()
	}

	// Shutdown WebSocket handler
	if s.wsHandler != nil {
		s.wsHandler.Shutdown()
	}

	// Cleanup all clients
	s.clientManager.CleanupAll()

	logger.Info("Server stopped")
}

// GetClientManager returns the client manager
func (s *Server) GetClientManager() *client.ClientManager {
	return s.clientManager
}

// ginCorsMiddleware returns a gin CORS middleware
func ginCorsMiddleware(enabled bool) gin.HandlerFunc {
	if !enabled {
		return func(c *gin.Context) {
			c.Next()
		}
	}

	return func(c *gin.Context) {
		origin := c.GetHeader("Origin")
		if origin != "" {
			c.Header("Access-Control-Allow-Origin", "*")
			c.Header("Access-Control-Allow-Methods", "POST, GET, OPTIONS, PUT, DELETE, UPDATE")
			c.Header("Access-Control-Allow-Headers", "Authorization, Content-Length, X-CSRF-Token, Token, session")
			c.Header("Access-Control-Expose-Headers", "Content-Length, Access-Control-Allow-Origin, Access-Control-Allow-Headers")
			c.Header("Access-Control-Allow-Credentials", "true")
		}

		// Handle preflight requests
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusOK)
			return
		}

		c.Next()
	}
}

// ginRouteReplaceMiddleware returns a gin route replacement middleware
func ginRouteReplaceMiddleware(enabled bool, prefix string) gin.HandlerFunc {
	if !enabled || prefix == "" {
		return func(c *gin.Context) {
			c.Next()
		}
	}

	return func(c *gin.Context) {
		// Replace the prefix
		newPath := strings.TrimPrefix(c.Request.URL.Path, prefix)
		if newPath == c.Request.URL.Path {
			// Prefix not found, pass through
			c.Next()
			return
		}
		if newPath == "" {
			newPath = "/"
		}
		// Modify request path
		c.Request.URL.Path = newPath
		c.Next()
	}
}
