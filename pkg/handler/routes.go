package handler

import (
	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/alert"
	"github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/middleware"
)

// Deps holds all handler dependencies for injection.
type Deps struct {
	UserRepo       repository.UserRepository
	GroupRepo      repository.GroupRepository
	SysConfigRepo  repository.SysConfigRepository
	ServerNodeRepo repository.ServerNodeRepository
	SysLogRepo     repository.SysLogRepository
	TraceRepo      repository.TraceRepository
	AlertRepo      repository.AlertRepository
	MetricRepo     repository.MetricRepository
}

// SetupWebRoutes 设置 Web 管理界面路由
func SetupWebRoutes(r *gin.Engine, deps Deps, alertEvaluator *alert.Evaluator, cfgSvc config.Service) {
	// Set SysLogRepository for audit logging
	SetSysLogRepository(deps.SysLogRepo)

	// Create auth middleware
	authMiddleware := middleware.NewAuthMiddleware()

	// Create handler instances with injected repositories
	userHandler := NewUserHandler(deps.UserRepo)
	groupHandler := NewGroupHandler(deps.GroupRepo)
	sysConfigHandler := NewSysConfigHandler(deps.SysConfigRepo, deps.ServerNodeRepo, deps.SysLogRepo, cfgSvc)
	anonymousHandler := NewAnonymousGroupHandler(deps.GroupRepo)
	metricHandler := NewMetricHandler(deps.MetricRepo)
	traceHandler := NewTraceHandler(deps.TraceRepo)
	alertHandler := NewAlertHandler(deps.AlertRepo, alertEvaluator)

	// API 路由组（需要认证）
	api := r.Group("/api")
	api.Use(
		func(c *gin.Context) {
			c.Set("configService", cfgSvc)
			c.Set("groupRepo", deps.GroupRepo)
			c.Next()
		},
		authMiddleware.Authenticate(),
		middleware.AnonymousAccessMiddleware(cfgSvc),
		middleware.RateLimitMiddleware(cfgSvc),
	)
	{
		users := api.Group("/users")
		users.Use(authMiddleware.RequireAdmin())
		{
			users.GET("", userHandler.List)
			users.POST("", userHandler.Add)
			users.PUT("/qps", userHandler.UpdateQps)
			users.DELETE("", userHandler.Delete)
		}

		currentUser := api.Group("/current")
		{
			currentUser.GET("", userHandler.GetCurrentUser)
			currentUser.POST("/password", userHandler.ChangePassword)
			currentUser.POST("/token/refresh", userHandler.RefreshToken)
		}

		groups := api.Group("/groups")
		{
			groups.GET("", groupHandler.List)
			groups.POST("", groupHandler.Create)
			groups.DELETE("", groupHandler.Delete)
			groups.GET("/:groupName", groupHandler.GetDetail)
			groups.PUT("/qps", groupHandler.UpdateQps)
			groups.GET("/:groupName/devices", groupHandler.GetDevices)
			groups.DELETE("/devices", groupHandler.DeleteDevice)
			groups.PUT("/devices/disable", groupHandler.DisableDevice)
			groups.GET("/:groupName/actions", groupHandler.GetActions)
			groups.POST("/actions", groupHandler.AddAction)
			groups.DELETE("/actions", groupHandler.DeleteAction)
		}

		anonGroups := api.Group("/anonymous-groups")
		{
			anonGroups.GET("", anonymousHandler.ListOptimized)
			anonGroups.DELETE("", anonymousHandler.Delete)
			anonGroups.POST("/convert", anonymousHandler.ConvertAnonymousGroup)
		}

		sysConfig := api.Group("/sysconfig")
		sysConfig.Use(authMiddleware.RequireAdmin())
		{
			sysConfig.GET("", sysConfigHandler.List)
			sysConfig.PUT("", sysConfigHandler.Update)
			sysConfig.GET("/nodes", sysConfigHandler.GetServerNodes)
			sysConfig.GET("/logs", sysConfigHandler.GetSysLogs)
			sysConfig.GET("/app-logs", sysConfigHandler.GetAppLogs)
		}

		metrics := api.Group("/metrics")
		{
			metrics.GET("", metricHandler.GetMetrics)
			metrics.GET("/list", metricHandler.GetMetricList)
			metrics.GET("/dashboard", metricHandler.GetDashboardData)
			metrics.GET("/latency/percentiles", metricHandler.GetLatencyPercentiles)
		}

		traces := api.Group("/traces")
		{
			traces.GET("", traceHandler.GetTraces)
			traces.GET("/stats", traceHandler.GetTraceStats)
			traces.GET("/timeline", traceHandler.GetTraceTimeline)
			traces.GET("/:traceId", traceHandler.GetTraceDetail)
			traces.GET("/:traceId/extra", traceHandler.GetTraceExtraData)
		}

		alerts := api.Group("/alerts")
		alerts.Use(authMiddleware.RequireAdmin())
		{
			alerts.GET("/rules", alertHandler.GetAlertRules)
			alerts.GET("/rules/:id", alertHandler.GetAlertRule)
			alerts.POST("/rules", alertHandler.CreateAlertRule)
			alerts.PUT("/rules/:id", alertHandler.UpdateAlertRule)
			alerts.DELETE("/rules/:id", alertHandler.DeleteAlertRule)
			alerts.GET("/history", alertHandler.GetAlertHistory)
		}
	}
}
