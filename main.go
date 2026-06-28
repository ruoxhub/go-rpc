// Rpc RPC Server - Go Implementation
package main

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
	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/alert"
	"github.com/mrh30000/go-rpc/pkg/client"
	pkgconfig "github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/deps"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/handler"
	"github.com/mrh30000/go-rpc/pkg/metrics"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/websocket"
	webui "github.com/mrh30000/go-rpc/web"
	"gorm.io/gorm"
)

var (
	port          int
	host          string
	debug         bool
	localDebug    bool
	resetMetrics  bool
)

func init() {
	flag.IntVar(&port, "port", 0, "Server port")
	flag.StringVar(&host, "host", "", "Server host")
	flag.BoolVar(&debug, "debug", false, "Enable debug logging")
	flag.BoolVar(&localDebug, "local-debug", false, "Enable local debug mode")
	flag.BoolVar(&resetMetrics, "reset-metrics", false, "Drop all metric tables on startup (AutoMigrate will recreate them). TEST-ENV ONLY.")
}

func main() {
	flag.Parse()

	cfg := &Config{
		Port:         port,
		Host:         host,
		Debug:        debug,
		LocalDebug:   localDebug,
		ResetMetrics: resetMetrics,
	}

	srv := NewServer(cfg)

	fmt.Printf("Starting Rpc RPC Server...\n")
	fmt.Printf("Host: %s, Port: %d\n", cfg.Host, cfg.Port)

	if err := srv.Start(); err != nil {
		fmt.Printf("Server error: %v\n", err)
	}
}

// Config holds server configuration
type Config struct {
	Port         int
	Host         string
	Debug        bool
	LocalDebug   bool
	ResetMetrics bool
}

func DefaultConfig() *Config {
	return &Config{
		Port:         5612,
		Host:         "0.0.0.0",
		Debug:        false,
		LocalDebug:   false,
		ResetMetrics: false,
	}
}

// Server represents the Rpc server
type Server struct {
	config           *Config
	serverConfig       *config.ServerConfig
	shutdown         chan struct{}
	eventBus         *eventbus.EventBus
	clientManager    *client.ClientManager
	httpServer       *handler.HTTPServer
	apiHandler       *handler.APIHandler
	wsHandler        *websocket.Handler
	timeoutManager   *forwarder.TimeoutManager
	metricsCollector metrics.MetricCollector
	alertEvaluator   *alert.Evaluator
	configService    pkgconfig.Service
	groupRepo        repository.GroupRepository
	db               *gorm.DB
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

// logFileOptions maps config.LogConfig to logger.FileOptions.
// Returns nil when serverConfig is nil so that InitLogger falls back
// to console-only output.
func logFileOptions(sc *config.ServerConfig) *logger.FileOptions {
	if sc == nil {
		return nil
	}
	lc := sc.Log
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
	config.LoadDotEnv()
	s.serverConfig = config.LoadServerConfigFromEnv()

	if s.config.Host != "" {
		s.serverConfig.Host = s.config.Host
	}
	if s.config.Port != 0 {
		s.serverConfig.Port = s.config.Port
	}
	s.config.Host = s.serverConfig.Host
	s.config.Port = s.serverConfig.Port

	if s.config.Debug {
		s.serverConfig.Mode = "debug"
	}

	logger.InitLogger(s.config.Debug, logFileOptions(s.serverConfig))

	disableDB := s.serverConfig.DisableDatabase
	disableMetrics := s.serverConfig.DisableMetrics
	disableAlert := s.serverConfig.DisableAlert

	if !disableDB {
		if err := database.InitFromConfig(
			s.serverConfig.Database.Host,
			s.serverConfig.Database.Port,
			s.serverConfig.Database.User,
			s.serverConfig.Database.Password,
			s.serverConfig.Database.DBName,
			s.serverConfig.Database.SSLMode,
		); err != nil {
			logger.Errorf("Failed to initialize database: %v", err)
			return fmt.Errorf("failed to initialize database: %w", err)
		}

		if err := database.ConfigurePool(
			s.serverConfig.Database.MaxOpenConns,
			s.serverConfig.Database.MaxIdleConns,
			s.serverConfig.Database.ConnMaxLifetime,
		); err != nil {
			logger.Errorf("Failed to configure database pool: %v", err)
			return fmt.Errorf("failed to configure database pool: %w", err)
		}

		if s.config.ResetMetrics {
			logger.Warn("-reset-metrics set: dropping metric tables (metric_minute, metric_hour, metric_day, metric_tag)")
			if err := database.ResetMetricTables(); err != nil {
				logger.Errorf("Failed to reset metric tables: %v", err)
				return fmt.Errorf("failed to reset metric tables: %w", err)
			}
			logger.Warn("Metric tables dropped; AutoMigrate will recreate them below")
		}

		if err := database.AutoMigrate(); err != nil {
			logger.Errorf("Failed to run database migration: %v", err)
			return fmt.Errorf("failed to run database migration: %w", err)
		}
		logger.Info("Database migration completed successfully")
		db := database.GetDB()
		s.db = db
		s.groupRepo = repository.NewGroupRepository(db)
		userRepo := repository.NewUserRepository(db)

		appDeps := &deps.AppDependencies{
			DB:            db,
			UserRepo:      userRepo,
			GroupRepo:     s.groupRepo,
			ConfigService: s.configService,
			EventBus:      s.eventBus,
		}

		// Wire via AppDependencies (new DI pattern)
		handler.SetUserRepository(appDeps.UserRepo)
		handler.SetLoginGroupRepository(appDeps.GroupRepo)
		middleware.SetTokenUserRepository(appDeps.UserRepo)

		// Verify LoginHandler constructor works with AppDependencies
		_ = handler.NewLoginHandler(appDeps.UserRepo)
		if !s.serverConfig.DisableTrace {
			middleware.StartBatchedTraceRecorder(
				repository.NewTraceRepository(db),
				s.serverConfig.TraceSampleRate,
				s.serverConfig.TraceBatchSize,
			)
		} else {
			logger.Info("Trace recording disabled (RPC_DISABLE_TRACE=true)")
		}
		// 注入 repository 和 eventBus，然后刷新配置
		s.configService.SetDependencies(
			repository.NewSysConfigRepository(db),
			s.eventBus,
		)
		if err := s.configService.Refresh(); err != nil {
			logger.Errorf("Failed to load config: %v", err)
		}
	} else {
		logger.Info("Running in DB-less mode (DisableDatabase=true)")
		logger.Warn("数据库未初始化，跳过配置刷新")
	}
	logger.Info("Config service started successfully")

	s.wsHandler = websocket.NewHandler(s.clientManager, s.timeoutManager, nil, s.eventBus, s.groupRepo)

	if !disableMetrics {
		var metricStore repository.MetricStore
		if !disableDB {
			metricStore = repository.NewMetricStore(s.db)
		}
		s.metricsCollector = metrics.NewCollector(1*time.Minute, metricStore)
	}
	s.apiHandler = handler.NewAPIHandler(s.clientManager, s.wsHandler, s.timeoutManager, s.metricsCollector, s.configService, s.eventBus, s.groupRepo)

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
			s.metricsCollector.Set("client.online", map[string]string{"group": e.Group}, float64(len(current)))
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

		if !disableDB {
			alertRepo := repository.NewAlertRepository(s.db)
			s.alertEvaluator.SetAlertRepo(alertRepo)

			metricQueryStore := repository.NewMetricStore(s.db)
			alertQueryStore := &alert.RepoMetricQueryStore{Inner: metricQueryStore}
			s.alertEvaluator.SetMetricStore(alertQueryStore)
			metricsReader.SetStore(alertQueryStore)
		}

		smtp := s.serverConfig.Alert.SMTP
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

	s.httpServer = handler.NewHTTPServer(s.newHTTPConfig(mode))

	corsEnabled := s.serverConfig.Cors
	routeReplaceEnabled := s.serverConfig.RouterReplace.IsEnable
	routePrefix := s.serverConfig.RouterReplace.ReplaceRoute
	corsOrigins := s.serverConfig.CorsOrigins

	s.httpServer.Use(
		middleware.CORSMiddleware(corsEnabled, corsOrigins),
		middleware.RouteReplaceMiddleware(routeReplaceEnabled, routePrefix),
		middleware.LoggingMiddleware(),
	)
	if !s.serverConfig.DisableTrace {
		s.httpServer.Use(middleware.TraceMiddleware())
	}

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
	// registerRoutes can be exercised by tests that bypass NewServer.
	// In that case s.serverConfig is nil; fall back to the default server config.
	yc := s.serverConfig
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
		business.DELETE("/kick", s.apiHandler.HandleKickClient)
	}

	if !disableWebAdmin {
		db := s.db
		deps := handler.Deps{
			UserRepo:       repository.NewUserRepository(db),
			GroupRepo:      repository.NewGroupRepository(db),
			ClientManager:  s.clientManager,
			SysConfigRepo:  repository.NewSysConfigRepository(db),
			ServerNodeRepo: repository.NewServerNodeRepository(db),
			SysLogRepo:     repository.NewSysLogRepository(db),
			TraceRepo:      repository.NewTraceRepository(db),
			AlertRepo:      repository.NewAlertRepository(db),
			MetricRepo:     repository.NewMetricRepository(db),
			DB:             db,
		}
		handler.SetupWebRoutes(s.httpServer.Engine(), deps, s.alertEvaluator, s.configService)
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
	rpcAPI.Use(func(c *gin.Context) {
		c.Set("configService", s.configService)
		c.Set("clientManager", s.clientManager)
		if s.groupRepo != nil {
			c.Set("groupRepo", s.groupRepo)
		}
		c.Next()
	})
	{
		if !disableDB {
			userInfo := rpcAPI.Group("/user-info")
			{
				userInfo.POST("/login", middleware.LoginRateLimitMiddleware(), handler.HandleLogin)
				userInfo.POST("/register", handler.HandleRegister)
				userInfo.GET("/userInfo", handler.HandleGetUserInfo)
			}
		}

		system := rpcAPI.Group("/system")
		{
			system.GET("/systemNotice", handler.HandleSystemNotice)
			system.GET("/systemInfo", handler.HandleSystemInfo)
		}

		if !disableDB {
			frontend := rpcAPI.Group("/frontend")
			{
				frontend.GET("/listGroup", handler.HandleFrontendListGroup)
				frontend.GET("/anonymousGroupList", handler.HandleFrontendAnonymousGroupList)
				frontend.GET("/groupDetail", handler.HandleFrontendGroupDetail)
			}
		}
	}
}

// optionalAuthGroup creates a route group that applies the optional auth middleware.
// Centralized so /business, /v1, and /api all share the same authentication shape.
func (s *Server) optionalAuthGroup(relativePath string) *gin.RouterGroup {
	group := s.httpServer.Group(relativePath)
	group.Use(middleware.OptionalAuth())
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

func (s *Server) newHTTPConfig(mode string) *handler.HTTPConfig {
	return &handler.HTTPConfig{
		Host:         s.config.Host,
		Port:         s.config.Port,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		Mode:         mode,
		LocalDebug:   s.config.LocalDebug,
	}
}

// negotiateSubprotocol 把客户端请求的 Sec-WebSocket-Protocol 原样回写到响应头，
// 满足浏览器“服务器必须在响应中确认所选子协议”的强制约定；无请求时返回 nil，
// 保持原有行为（不做子协议协商）。
func negotiateSubprotocol(c *gin.Context) http.Header {
	if proto := c.GetHeader("Sec-WebSocket-Protocol"); proto != "" {
		h := http.Header{}
		h.Set("Sec-WebSocket-Protocol", proto)
		return h
	}
	return nil
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

	wsConn, err := s.httpServer.WSUpgrader().Upgrade(c.Writer, c.Request, negotiateSubprotocol(c))
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
	// 1) 全局 IP 白名单优先：命中即放行，跳过一切 DB 查询与 token/子协议校验。
	if s.configService != nil {
		if globalIPs := s.configService.GetConfig(pkgconfig.ConfigKeyAllowedIPs); globalIPs != "" {
			if middleware.IPInList(c.ClientIP(), globalIPs) {
				return true
			}
		}
	}

	if s.groupRepo == nil {
		return true
	}

	group, err := middleware.LookupGroupConfig(groupName, s.groupRepo.FindGroupByName)
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

	// 2) 子协议鉴权（隐蔽）：Sec-WebSocket-Protocol: sekiro-auth.<token>。
	// 3) 标准鉴权：Authorization Bearer / sekiro-token header / query / form。
	token := middleware.ExtractTokenFromSubprotocol(c)
	if token == "" {
		token = middleware.ExtractAuthTokenFromRequest(c, false)
	}
	if token == "" {
		c.JSON(http.StatusUnauthorized, gin.H{
			"error": "registered group requires a valid rpc token",
		})
		return false
	}
	user, err := middleware.FindUserByToken(token)
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

	if s.shutdown != nil {
		select {
		case <-s.shutdown:
			// Already closed
		default:
			close(s.shutdown)
		}
	}

	// Cancel all WebSocket handler goroutines
	if s.wsCancel != nil {
		s.wsCancel()
	}

	if s.httpServer != nil {
		s.httpServer.Shutdown()
	}
	// Flush any pending batched trace records after HTTP traffic has drained.
	middleware.ShutdownTraceRecorder()
	// Stop auth cache GC goroutines to avoid leak on exit.
	middleware.ShutdownCaches()
	if s.wsHandler != nil {
		s.wsHandler.Shutdown()
	}
	if s.alertEvaluator != nil {
		s.alertEvaluator.Stop()
	}
	if s.metricsCollector != nil {
		s.metricsCollector.Shutdown()
	}

	if s.clientManager != nil {
		s.clientManager.Stop()
		s.clientManager.CleanupAll()
	}

	if s.db != nil {
		if sqlDB, err := s.db.DB(); err == nil {
			if err := sqlDB.Close(); err != nil {
				logger.Errorf("Failed to close database pool: %v", err)
			}
		}
	}

	logger.Info("Server stopped")
}

func (s *Server) GetClientManager() *client.ClientManager {
	return s.clientManager
}

func (s *Server) GetMetricsCollector() metrics.MetricCollector {
	return s.metricsCollector
}
