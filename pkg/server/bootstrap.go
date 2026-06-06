// Package server implements the Rpc server
package server

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/alert"
	"github.com/mrh30000/go-rpc/pkg/server/api"
	"github.com/mrh30000/go-rpc/pkg/server/client"
	pkgconfig "github.com/mrh30000/go-rpc/pkg/server/config"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
	"github.com/mrh30000/go-rpc/pkg/server/handlers"
	"github.com/mrh30000/go-rpc/pkg/server/metrics"
	"github.com/mrh30000/go-rpc/pkg/server/middleware"
	"github.com/mrh30000/go-rpc/pkg/server/websocket"
	webui "github.com/mrh30000/go-rpc/web"
)

// Config holds server configuration
type Config struct {
	Port       int
	Host       string
	Debug      bool
	LocalDebug bool
	ConfigPath string
}

func DefaultConfig() *Config {
	return &Config{
		Port:       5612,
		Host:       "0.0.0.0",
		Debug:      false,
		LocalDebug: false,
		ConfigPath: "config.yaml",
	}
}

// Server represents the Rpc server
type Server struct {
	config           *Config
	yamlConfig       *config.ServerConfig
	shutdown         chan struct{}
	eventBus         *eventbus.EventBus
	clientManager    *client.ClientManager
	httpServer       *api.HTTPServer
	apiHandler       *api.APIHandler
	wsHandler        *websocket.Handler
	timeoutManager   *forwarder.TimeoutManager
	metricsCollector metrics.MetricCollector
	alertEvaluator   *alert.Evaluator
	configService    pkgconfig.Service
	// wsCancel cancels all WebSocket handler goroutines on shutdown
	wsCtx    context.Context
	wsCancel context.CancelFunc
}

func NewServer(config *Config) *Server {
	wsCtx, wsCancel := context.WithCancel(context.Background())
	eb := eventbus.New()
	cm := client.NewClientManager()
	cm.SetEventBus(eb)

	return &Server{
		config:         config,
		shutdown:       make(chan struct{}),
		eventBus:       eb,
		clientManager:  cm,
		timeoutManager: forwarder.NewTimeoutManager(nil),
		configService:  pkgconfig.NewService(),
		wsCtx:          wsCtx,
		wsCancel:       wsCancel,
	}
}

func (s *Server) loadYAMLConfig() error {
	if s.config.ConfigPath == "" {
		s.config.ConfigPath = "config.yaml"
	}

	var err error
	s.yamlConfig, err = config.LoadServerConfig(s.config.ConfigPath)
	if err != nil {
		logger.Warningf("Failed to load YAML config: %v, using defaults", err)
		s.yamlConfig = config.DefaultServerConfig()
	}
	return nil
}

func (s *Server) applyYAMLConfig() {
	if s.yamlConfig == nil {
		return
	}
	if s.config.Host == "" {
		s.config.Host = s.yamlConfig.Host
	}
	if s.config.Port == 0 {
		s.config.Port = s.yamlConfig.Port
	}
	if s.config.Host == "" {
		s.config.Host = "0.0.0.0"
	}
	if s.config.Port == 0 {
		s.config.Port = 5612
	}
	if s.yamlConfig.Mode == "debug" {
		s.config.Debug = true
	}
}

// logFileOptions maps config.LogConfig to logger.FileOptions.
// Returns nil when yamlConfig is nil so that InitLogger falls back
// to console-only output.
func logFileOptions(yc *config.ServerConfig) *logger.FileOptions {
	if yc == nil {
		return nil
	}
	lc := yc.Log
	return &logger.FileOptions{
		Enabled:    lc.Dir != "" && lc.Filename != "",
		Dir:        lc.Dir,
		Filename:   lc.Filename,
		MaxSize:    lc.MaxSize,
		MaxBackups: lc.MaxBackups,
		MaxAge:     lc.MaxAge,
		Compress:   lc.Compress,
	}
}

func (s *Server) Start() error {
	s.loadYAMLConfig()
	s.applyYAMLConfig()

	logger.InitLogger(s.config.Debug, logFileOptions(s.yamlConfig))

	disableDB := s.yamlConfig.DisableDatabase
	disableMetrics := s.yamlConfig.DisableMetrics
	disableAlert := s.yamlConfig.DisableAlert

	if !disableDB {
		if err := database.InitFromConfig(
			s.yamlConfig.Database.Host,
			s.yamlConfig.Database.Port,
			s.yamlConfig.Database.User,
			s.yamlConfig.Database.Password,
			s.yamlConfig.Database.DBName,
			s.yamlConfig.Database.SSLMode,
		); err != nil {
			logger.Errorf("Failed to initialize database: %v", err)
			return fmt.Errorf("failed to initialize database: %w", err)
		}

		if err := database.AutoMigrate(); err != nil {
			logger.Errorf("Failed to run database migration: %v", err)
			return fmt.Errorf("failed to run database migration: %w", err)
		}
		logger.Info("Database migration completed successfully")
	} else {
		logger.Info("Running in DB-less mode (DisableDatabase=true)")
	}

	// 启动配置服务（仅启动时加载一次，后续在配置更新时手动触发刷新）
	if err := s.configService.Refresh(); err != nil {
		logger.Errorf("Failed to load config: %v", err)
		// 配置加载失败不影响服务器启动
	}
	logger.Info("Config service started successfully")

	s.wsHandler = websocket.NewHandler(s.clientManager, s.timeoutManager, nil, s.eventBus)

	if !disableMetrics {
		s.metricsCollector = metrics.NewCollector(1 * time.Minute)
	}
	s.apiHandler = api.NewAPIHandler(s.clientManager, s.wsHandler, s.timeoutManager, s.metricsCollector, s.configService, s.eventBus)

	// 注册事件订阅：客户端连接/断开 → 更新在线客户端数 Gauge
	if s.metricsCollector != nil {
		s.eventBus.Subscribe(eventbus.EventClientConnect, func(event interface{}) {
			e := event.(*eventbus.ClientConnectEvent)
			current := s.clientManager.GetClientsByGroup(e.Group)
			s.metricsCollector.Set("client.online", map[string]string{"group": e.Group}, float64(len(current)))
		})
		s.eventBus.Subscribe(eventbus.EventClientDisconnect, func(event interface{}) {
			e := event.(*eventbus.ClientDisconnectEvent)
			current := s.clientManager.GetClientsByGroup(e.Group)
			count := float64(0)
			if current != nil {
				count = float64(len(current))
			}
			s.metricsCollector.Set("client.online", map[string]string{"group": e.Group}, count)
		})
	}

	// 注册事件订阅：健康降级 → 记录告警
	s.eventBus.Subscribe(eventbus.EventClientHealthDegraded, func(event interface{}) {
		e := event.(*eventbus.ClientHealthDegradedEvent)
		logger.Warnf("Client health degraded: group=%s, clientId=%s, failCount=%d",
			e.Group, e.ClientID, e.FailCount)
	})

	if !disableAlert {
		metricsReader := alert.NewDefaultMetricsReader()
		s.alertEvaluator = alert.NewEvaluator(1*time.Minute, metricsReader)

		smtp := s.yamlConfig.Alert.SMTP
		s.alertEvaluator.SetSMTPConfig(alert.SMTPConfig{
			Host:     smtp.Host,
			Port:     smtp.Port,
			Username: smtp.Username,
			Password: smtp.Password,
			From:     smtp.From,
			UseTLS:   smtp.UseTLS,
		})

		s.alertEvaluator.Start(context.Background())
	}

	mode := gin.ReleaseMode
	if s.config.Debug {
		mode = gin.DebugMode
	}

	s.httpServer = api.NewHTTPServer(s.newHTTPConfig(mode))

	corsEnabled := s.yamlConfig.Cors
	routeReplaceEnabled := s.yamlConfig.RouterReplace.IsEnable
	routePrefix := s.yamlConfig.RouterReplace.ReplaceRoute
	corsOrigins := s.yamlConfig.CorsOrigins

	s.httpServer.Use(
		ginCorsMiddleware(corsEnabled, corsOrigins),
		ginRouteReplaceMiddleware(routeReplaceEnabled, routePrefix),
		middleware.LoggingMiddleware(),
		middleware.TraceMiddleware(),
	)

	s.registerRoutes()

	addr := fmt.Sprintf("%s:%d", s.config.Host, s.config.Port)
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to create listener: %w", err)
	}

	logger.Infof("Rpc server starting on %s", addr)
	logger.Infof("CORS enabled: %v", corsEnabled)
	logger.Debug("Legacy detector path is not wired into the active server bootstrap")
	if routeReplaceEnabled {
		logger.Infof("Route prefix replacement enabled: %s", routePrefix)
	}
	logger.Info("Welcome to use Rpc framework")

	go func() {
		if err := s.httpServer.Server().Serve(listener); err != nil && err != http.ErrServerClosed {
			logger.Errorf("HTTP server error: %v", err)
		}
	}()

	s.waitForShutdown()
	return nil
}

func (s *Server) registerRoutes() {
	// registerRoutes can be exercised by tests that bypass NewServer/loadYAMLConfig.
	// In that case s.yamlConfig is nil; fall back to the default server config so
	// yaml-driven toggles still resolve to a defined value.
	yc := s.yamlConfig
	if yc == nil {
		yc = config.DefaultServerConfig()
	}
	disableWebAdmin := yc.DisableWebAdmin
	disableDB := yc.DisableDatabase

	if !disableWebAdmin {
		webui.RegisterRoutes(s.httpServer.Engine())
		s.httpServer.Engine().GET("/", webui.ServeIndex)
	}

	// 健康检查端点
	s.httpServer.Engine().GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status":    "healthy",
			"timestamp": time.Now().Format(time.RFC3339),
			"version":   "1.0.0",
		})
	})

	s.httpServer.Engine().NoRoute(func(c *gin.Context) {
		if isAPIPath(c.Request.URL.Path) {
			c.JSON(404, gin.H{"error": "Not found"})
			return
		}
		if !disableWebAdmin {
			webui.ServePathOrIndex(c)
			return
		}
		c.JSON(404, gin.H{"error": "Not found"})
	})

	business := s.optionalAuthGroup("/business")
	{
		business.GET("/groupList", s.apiHandler.HandleGroupList)
		business.GET("/clientQueue", s.apiHandler.HandleClientQueue)
		business.Any("/invoke", s.apiHandler.HandleInvoke)
		business.GET("/register", s.handleRegister)
	}

	if !disableWebAdmin {
		db := database.GetDB()
		deps := handlers.Deps{
			UserRepo:       repository.NewUserRepository(db),
			GroupRepo:      repository.NewGroupRepository(db),
			SysConfigRepo:  repository.NewSysConfigRepository(db),
			ServerNodeRepo: repository.NewServerNodeRepository(db),
			SysLogRepo:     repository.NewSysLogRepository(db),
			TraceRepo:      repository.NewTraceRepository(db),
			AlertRepo:      repository.NewAlertRepository(db),
			MetricRepo:     repository.NewMetricRepository(db),
		}
		handlers.SetupWebRoutes(s.httpServer.Engine(), deps, s.alertEvaluator, s.configService)
	}

	v1 := s.optionalAuthGroup("/v1")
	{
		v1.POST("/chat/completions", s.apiHandler.HandleChatCompletions)
	}

	// /api/* OpenAI-compatible surface for provider-specific routing.
	// Currently routes /api/chat/completions to the qwenai browser-extension provider.
	apiGroup := s.optionalAuthGroup("/api")
	{
		apiGroup.POST("/chat/completions", s.apiHandler.HandleQwenChatCompletions)
	}

	rpcAPI := s.httpServer.Group("/rpc-api")
	// 为 /rpc-api 路由添加配置服务和仓储上下文
	rpcAPI.Use(func(c *gin.Context) {
		c.Set("configService", s.configService)
		if !disableDB {
			c.Set("groupRepo", repository.NewGroupRepository(database.GetDB()))
		}
		c.Next()
	})
	{
		if !disableDB {
			userInfo := rpcAPI.Group("/user-info")
			{
				userInfo.POST("/login", handlers.HandleLogin)
				userInfo.POST("/register", handlers.HandleRegister)
				userInfo.GET("/userInfo", handlers.HandleGetUserInfo)
			}
		}

		system := rpcAPI.Group("/system")
		{
			system.GET("/systemNotice", handlers.HandleSystemNotice)
			system.GET("/systemInfo", handlers.HandleSystemInfo)
		}

		if !disableDB {
			frontend := rpcAPI.Group("/frontend")
			{
				frontend.GET("/listGroup", handlers.HandleFrontendListGroup)
				frontend.GET("/anonymousGroupList", handlers.HandleFrontendAnonymousGroupList)
				frontend.GET("/groupDetail", handlers.HandleFrontendGroupDetail)
			}
		}
	}
}

// optionalAuthGroup creates a route group that applies the optional auth middleware.
// Centralized so /business, /v1, and /api all share the same authentication shape.
func (s *Server) optionalAuthGroup(relativePath string) *gin.RouterGroup {
	group := s.httpServer.Group(relativePath)
	group.Use(middleware.NewAuthMiddleware().OptionalAuth())
	return group
}

// apiPathPrefixes lists URL path prefixes that should return JSON 404 instead
// of falling through to the web admin index. Used by the global NoRoute handler.
var apiPathPrefixes = []string{"/api/", "/rpc-api/", "/business/", "/v1/"}

func isAPIPath(path string) bool {
	for _, prefix := range apiPathPrefixes {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}
	return false
}

func (s *Server) newHTTPConfig(mode string) *api.Config {
	return &api.Config{
		Host:         s.config.Host,
		Port:         s.config.Port,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		Mode:         mode,
		LocalDebug:   s.config.LocalDebug,
	}
}

func (s *Server) handleRegister(c *gin.Context) {
	group := c.Query("group")
	clientID := c.Query("clientId")

	if group == "" || clientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "group and clientId parameters required",
		})
		return
	}
	if !s.authorizeRegisterAccess(c, group) {
		return
	}

	wsConn, err := s.httpServer.WSUpgrader().Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		logger.Errorf("WebSocket upgrade error: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "WebSocket upgrade failed",
		})
		return
	}

	go s.wsHandler.HandleConnection(s.wsCtx, wsConn, group, clientID)
}

func (s *Server) authorizeRegisterAccess(c *gin.Context, groupName string) bool {
	db := database.GetDB()
	if db == nil {
		return true
	}

	group, err := middleware.LookupGroupConfig(groupName, func(name string) (*model.GroupConfig, error) {
		var g model.GroupConfig
		result := db.Where("group_name = ?", name).Limit(1).Find(&g)
		if result.Error != nil {
			return nil, result.Error
		}
		if result.RowsAffected == 0 {
			return nil, nil
		}
		return &g, nil
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "failed to verify group access",
		})
		return false
	}
	if group == nil {
		// 未找到分组则视为公开分组，允许任意注册
		return true
	}

	user, err := middleware.FindUserByToken(middleware.ExtractAuthTokenFromRequest(c))
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{
			"error": "registered group requires a valid rpc token",
		})
		return false
	}
	if !user.IsAdmin && user.UserName != group.UserName {
		c.JSON(http.StatusForbidden, gin.H{
			"error": "no access to registered group",
		})
		return false
	}

	return true
}

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

func (s *Server) Shutdown() {
	logger.Info("Shutting down server...")

	select {
	case <-s.shutdown:
		// Already closed
	default:
		close(s.shutdown)
	}

	// Cancel all WebSocket handler goroutines
	if s.wsCancel != nil {
		s.wsCancel()
	}

	if s.httpServer != nil {
		s.httpServer.Shutdown()
	}
	if s.wsHandler != nil {
		s.wsHandler.Shutdown()
	}
	if s.alertEvaluator != nil {
		s.alertEvaluator.Stop()
	}
	if s.metricsCollector != nil {
		s.metricsCollector.Shutdown()
	}

	s.clientManager.Stop()
	s.clientManager.CleanupAll()
	logger.Info("Server stopped")
}

func (s *Server) GetClientManager() *client.ClientManager {
	return s.clientManager
}

func (s *Server) GetMetricsCollector() metrics.MetricCollector {
	return s.metricsCollector
}

func ginCorsMiddleware(enabled bool, whitelist []string) gin.HandlerFunc {
	if !enabled {
		return func(c *gin.Context) {
			c.Next()
		}
	}

	return func(c *gin.Context) {
		origin := c.GetHeader("Origin")
		if origin != "" && isOriginAllowed(origin, whitelist) {
			c.Header("Access-Control-Allow-Origin", origin)
			c.Header("Access-Control-Allow-Credentials", "true")
			c.Header("Access-Control-Allow-Methods", "POST, GET, OPTIONS, PUT, DELETE, UPDATE")
			c.Header("Access-Control-Allow-Headers", "Authorization, Content-Length, X-CSRF-Token, Token, session")
			c.Header("Access-Control-Expose-Headers", "Content-Length, Access-Control-Allow-Origin, Access-Control-Allow-Headers")
		}

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusOK)
			return
		}

		c.Next()
	}
}

// isOriginAllowed checks if the origin is allowed by the whitelist.
// An empty whitelist allows all origins.
func isOriginAllowed(origin string, whitelist []string) bool {
	if len(whitelist) == 0 {
		return true
	}
	for _, w := range whitelist {
		if w == origin {
			return true
		}
	}
	return false
}

func ginRouteReplaceMiddleware(enabled bool, prefix string) gin.HandlerFunc {
	if !enabled || prefix == "" {
		return func(c *gin.Context) {
			c.Next()
		}
	}

	return func(c *gin.Context) {
		newPath := strings.TrimPrefix(c.Request.URL.Path, prefix)
		if newPath == c.Request.URL.Path {
			c.Next()
			return
		}
		if newPath == "" {
			newPath = "/"
		}
		c.Request.URL.Path = newPath
		c.Next()
	}
}
