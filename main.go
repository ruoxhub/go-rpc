// Rpc RPC Server - Go Implementation
package main

import (
	"context"
	"errors"
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
	"github.com/mrh30000/go-rpc/pkg/protocol"
	"github.com/mrh30000/go-rpc/pkg/websocket"
	webui "github.com/mrh30000/go-rpc/web"
	"gorm.io/gorm"
)

var (
	port         int
	host         string
	debug        bool
	localDebug   bool
	resetMetrics bool

	// version 在构建时通过 -ldflags "-X main.version=..." 注入。
	// 默认 "dev" 用于本地开发,docker build 可通过 --build-arg VERSION=<tag> 覆盖。
	version = "dev"
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
	serverConfig     *config.ServerConfig
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
	authMW           *middleware.AuthMiddleware
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

	logger.Infof("Rpc RPC Server version: %s", version)

	// 生产环境安全检查:拒绝使用默认数据库密码,防止误部署导致数据泄露。
	isReleaseMode := s.serverConfig.Mode == "release" || !s.config.Debug
	dbCfg := s.serverConfig.Database
	if isReleaseMode && !s.serverConfig.DisableDatabase {
		if dbCfg.User == "postgres" && dbCfg.Password == "postgres" {
			return fmt.Errorf("refusing to start in release mode with default database credentials " +
				"(postgres/postgres): set RPC_DB_USER and RPC_DB_PASSWORD to non-default values")
		}
	}

	// 生产环境安全检查:拒绝 -reset-metrics,防止误操作清空生产指标数据。
	if resetMetrics && isReleaseMode {
		return fmt.Errorf("-reset-metrics is forbidden in release mode " +
			"(it drops all metric tables); restart with RPC_MODE=debug or remove the flag")
	}

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
			s.serverConfig.Database.ConnMaxIdleTime,
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

		if s.serverConfig.DisableAutoMigrate {
			logger.Info("AutoMigrate skipped (RPC_DISABLE_AUTO_MIGRATE=true); " +
				"ensure schema is managed via deploy/postgres/migration/ scripts")
		} else {
			if err := database.AutoMigrate(); err != nil {
				logger.Errorf("Failed to run database migration: %v", err)
				return fmt.Errorf("failed to run database migration: %w", err)
			}
			logger.Info("Database migration completed successfully")
		}
		db := database.GetDB()
		s.db = db
		s.groupRepo = repository.NewGroupRepository(db)
		userRepo := repository.NewUserRepository(db)

		// 初始化 metrics collector（须早于 authMW 构造，使 auth.deny 埋点真正生效）
		if !disableMetrics {
			s.metricsCollector = metrics.NewCollector(1*time.Minute, repository.NewMetricStore(db))
		}

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

		// 创建 AuthMiddleware 实例（B4 DI 改造）
		s.authMW = middleware.NewAuthMiddleware(
			appDeps.UserRepo,
			s.groupRepo.FindGroupByName,
			middleware.DefaultTokenCache(),
			middleware.DefaultGroupCache(),
			s.metricsCollector,
		)

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
		logger.Warn("SECURITY: DB-less mode allows anonymous access to /business/*; do not expose this server to untrusted networks")
		logger.Warn("数据库未初始化，跳过配置刷新")
		// DB-less 模式下仍创建无 store 的 collector（flush 时 warn，不落库），保留原行为
		if !disableMetrics {
			s.metricsCollector = metrics.NewCollector(1*time.Minute, nil)
		}
	}
	logger.Info("Config service started successfully")

	s.wsHandler = websocket.NewHandler(s.clientManager, s.timeoutManager, nil, s.eventBus, s.groupRepo)

	s.apiHandler = handler.NewAPIHandlerWithDBLessMode(s.clientManager, s.wsHandler, s.timeoutManager, s.metricsCollector, s.configService, s.eventBus, s.groupRepo, s.authMW, s.serverConfig != nil && s.serverConfig.DisableDatabase)

	// 注册事件订阅：客户端连接/断开 → 更新在线客户端数 Gauge
	if s.metricsCollector != nil {
		eventbus.SubscribeTyped(s.eventBus, eventbus.EventClientConnect, func(e eventbus.ClientConnectEvent) {
			current := s.clientManager.GetClientsByGroup(e.Group)
			s.metricsCollector.Set("client.online", map[string]string{"group": e.Group}, float64(len(current)))
		})
		eventbus.SubscribeTyped(s.eventBus, eventbus.EventClientDisconnect, func(e eventbus.ClientDisconnectEvent) {
			current := s.clientManager.GetClientsByGroup(e.Group)
			s.metricsCollector.Set("client.online", map[string]string{"group": e.Group}, float64(len(current)))
		})
	}

	// 注册事件订阅：健康降级 → 记录告警
	eventbus.SubscribeTyped(s.eventBus, eventbus.EventClientHealthDegraded, func(e eventbus.ClientHealthDegradedEvent) {
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

	// 监听地址:HTTPS 启用时优先使用 HttpsListen,否则用 host:port。
	useTLS := s.serverConfig.HttpsServices.IsEnable
	addr := fmt.Sprintf("%s:%d", s.config.Host, s.config.Port)
	if useTLS && s.serverConfig.HttpsServices.HttpsListen != "" {
		addr = s.serverConfig.HttpsServices.HttpsListen
	}

	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to create listener: %w", err)
	}

	scheme := "http"
	if useTLS {
		scheme = "https"
	}
	logger.Infof("Rpc server starting on %s://%s", scheme, addr)
	logger.Infof("CORS enabled: %v", corsEnabled)
	logger.Debug("Legacy detector path is not wired into the active server bootstrap")
	if routeReplaceEnabled {
		logger.Infof("Route prefix replacement enabled: %s", routePrefix)
	}
	if useTLS {
		logger.Infof("TLS enabled: pem=%s key=%s",
			s.serverConfig.HttpsServices.PemPath, s.serverConfig.HttpsServices.KeyPath)
	}
	logger.Info("Welcome to use Rpc framework")

	go func() {
		if useTLS {
			if err := s.httpServer.Server().ServeTLS(
				listener,
				s.serverConfig.HttpsServices.PemPath,
				s.serverConfig.HttpsServices.KeyPath,
			); err != nil && err != http.ErrServerClosed {
				logger.Errorf("HTTPS server error: %v", err)
			}
		} else {
			if err := s.httpServer.Server().Serve(listener); err != nil && err != http.ErrServerClosed {
				logger.Errorf("HTTP server error: %v", err)
			}
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
	// /live: 进程存活探针,恒返回 200,用于 K8s livenessProbe(无需鉴权)。
	s.httpServer.Engine().GET("/live", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status":    "alive",
			"timestamp": time.Now().Format(time.RFC3339),
			"version":   version,
		})
	})

	// /ready: 就绪探针,检查关键依赖(DB)是否可用,用于 K8s readinessProbe。
	// DB 不可用时返回 503,使流量不路由到该实例。
	s.httpServer.Engine().GET("/ready", func(c *gin.Context) {
		if s.db != nil {
			if sqlDB, err := s.db.DB(); err == nil {
				if err := sqlDB.Ping(); err != nil {
					c.JSON(503, gin.H{
						"status":    "not ready",
						"reason":    "database ping failed",
						"timestamp": time.Now().Format(time.RFC3339),
					})
					return
				}
			} else {
				c.JSON(503, gin.H{
					"status":    "not ready",
					"reason":    "database connection unavailable",
					"timestamp": time.Now().Format(time.RFC3339),
				})
				return
			}
		}
		c.JSON(200, gin.H{
			"status":    "ready",
			"timestamp": time.Now().Format(time.RFC3339),
			"version":   version,
		})
	})

	// /health: 向后兼容别名,等同于 /live。
	s.httpServer.Engine().GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status":    "healthy",
			"timestamp": time.Now().Format(time.RFC3339),
			"version":   version,
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
		webDeps := handler.Deps{
			AppDependencies: &deps.AppDependencies{
				DB:            db,
				UserRepo:      repository.NewUserRepository(db),
				GroupRepo:     repository.NewGroupRepository(db),
				ConfigService: s.configService,
				EventBus:      s.eventBus,
			},
			ClientManager:    s.clientManager,
			SysConfigRepo:    repository.NewSysConfigRepository(db),
			ServerNodeRepo:   repository.NewServerNodeRepository(db),
			SysLogRepo:       repository.NewSysLogRepository(db),
			TraceRepo:        repository.NewTraceRepository(db),
			AlertRepo:        repository.NewAlertRepository(db),
			MetricRepo:       repository.NewMetricRepository(db),
			AuthMW:           s.authMW,
			MetricsCollector: s.metricsCollector,
		}
		handler.SetupWebRoutes(s.httpServer.Engine(), webDeps, s.alertEvaluator, s.configService)
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

func (s *Server) negotiateRegistration(c *gin.Context) (protocol.Registration, bool) {
	if s.serverConfig == nil || !s.serverConfig.CapabilityNegotiation {
		return protocol.LegacyRegistration(), true
	}
	registration, err := protocol.NegotiateRegistration(
		c.Query("protocol_version"),
		c.Query("capabilities"),
		[]string{protocol.CapabilityInvocationContextV1},
	)
	switch {
	case errors.Is(err, protocol.ErrUnsupportedProtocolVersion):
		c.JSON(http.StatusUpgradeRequired, gin.H{"error": err.Error()})
		return protocol.Registration{}, false
	case err != nil:
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return protocol.Registration{}, false
	default:
		return registration, true
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
	registration, ok := s.negotiateRegistration(c)
	if !ok {
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

	go s.wsHandler.HandleConnectionWithRegistration(s.wsCtx, wsConn, group, clientID, registration)
}

func (s *Server) authorizeRegisterAccess(c *gin.Context, groupName string) bool {
	// DB-less mode intentionally exposes /business/* without authentication.
	// Check the explicit mode flag rather than inferring it from nil repositories,
	// so broken database-mode dependency wiring remains fail-closed.
	if s.serverConfig != nil && s.serverConfig.DisableDatabase {
		return true
	}

	// 1) 全局 IP 白名单优先：命中即放行，跳过一切 DB 查询与 token/子协议校验。
	if s.configService != nil {
		if globalIPs := s.configService.GetConfig(pkgconfig.ConfigKeyAllowedIPs); globalIPs != "" {
			if middleware.IPInList(c.ClientIP(), globalIPs) {
				return true
			}
		}
	}

	// Fail closed: without groupRepo/authMW we cannot verify ownership.
	if s.groupRepo == nil || s.authMW == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"error": "group access verification unavailable",
		})
		return false
	}

	group, err := s.authMW.LookupGroupConfig(groupName)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "failed to verify group access",
		})
		return false
	}
	if group == nil {
		// Anonymous / unregistered group: only allow when anonymous access is enabled.
		if s.configService != nil && !s.configService.GetConfigBool(pkgconfig.ConfigKeyAllowAnonymousAccess, true) {
			c.JSON(http.StatusForbidden, gin.H{
				"error": "anonymous group registration is disabled",
			})
			return false
		}
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
	user, err := s.authMW.FindUserByToken(token)
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

	// 1. 先停止 HTTP Server:拒绝新连接,等待 in-flight HTTP 请求处理完毕。
	//    此时 WebSocket 客户端仍在线,RPC 响应仍可回传,让调用方拿到正常结果。
	if s.httpServer != nil {
		logger.Info("Draining HTTP connections (waiting for in-flight requests)...")
		if err := s.httpServer.Shutdown(); err != nil {
			logger.Errorf("HTTP server shutdown error: %v", err)
		}
	}

	// 2. 等待 in-flight RPC 排空(最多 drainGracePeriod)。
	//    httpServer.Shutdown 已等待 handler 返回,但 RPC handler 内部
	//    阻塞在 timeoutManager.Wait() 上。这里给一个额外的排空窗口,
	//    让尚未完成的 RPC 有机会收到响应或自然超时。
	s.drainInflight(10 * time.Second)

	// 3. 取消 WebSocket handler goroutines,断开所有客户端连接。
	if s.wsCancel != nil {
		s.wsCancel()
	}

	// 4. 关闭 timeout manager(强制关闭剩余的 invoke/stream 记录)。
	// Flush any pending batched trace records after HTTP traffic has drained.
	middleware.ShutdownTraceRecorder()
	// Stop auth cache GC goroutines to avoid leak on exit.
	if s.authMW != nil {
		s.authMW.Shutdown()
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

// drainInflight 等待 in-flight RPC 请求(unary + stream)排空,最多等待 maxWait。
// 在此期间 WebSocket 客户端仍在线,响应可正常回传。
func (s *Server) drainInflight(maxWait time.Duration) {
	if s.timeoutManager == nil {
		return
	}
	deadline := time.Now().Add(maxWait)
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	for {
		count := s.timeoutManager.Count() + s.timeoutManager.StreamCount()
		if count == 0 {
			logger.Info("All in-flight RPC requests drained")
			return
		}
		if time.Now().After(deadline) {
			logger.Warnf("Drain timeout: %d in-flight RPC request(s) still pending, proceeding with shutdown", count)
			return
		}
		logger.Infof("Waiting for %d in-flight RPC request(s) to drain...", count)
		<-ticker.C
	}
}

func (s *Server) GetClientManager() *client.ClientManager {
	return s.clientManager
}

func (s *Server) GetMetricsCollector() metrics.MetricCollector {
	return s.metricsCollector
}
