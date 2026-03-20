package handlers

import (
	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/server/middleware"
)

// SetupWebRoutes 设置 Web 管理界面路由
func SetupWebRoutes(r *gin.Engine) {
	// 创建认证中间件实例
	authMiddleware := middleware.NewAuthMiddleware()

	// 创建处理器实例
	userHandler := NewUserHandler()
	groupHandler := NewGroupHandler()
	sysConfigHandler := NewSysConfigHandler()
	anonymousHandler := NewAnonymousGroupHandler()
	metricHandler := NewMetricHandler()

	// API 路由组（需要认证）
	api := r.Group("/api")
	api.Use(authMiddleware.Authenticate()) // 应用认证中间件
	{
		// 用户管理
		users := api.Group("/users")
		{
			users.GET("", userHandler.List)
			users.POST("", userHandler.Add)
			users.PUT("/qps", userHandler.UpdateQps)
			users.DELETE("", userHandler.Delete)
		}

		// 当前用户
		currentUser := api.Group("/current")
		{
			currentUser.GET("", userHandler.GetCurrentUser)
			currentUser.POST("/password", userHandler.ChangePassword)
			currentUser.POST("/token/refresh", userHandler.RefreshToken)
		}

		// 分组管理
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

		// 匿名分组
		anonGroups := api.Group("/anonymous-groups")
		{
			anonGroups.GET("", anonymousHandler.List)
		}

		// 系统配置
		sysConfig := api.Group("/sysconfig")
		{
			sysConfig.GET("", sysConfigHandler.List)
			sysConfig.PUT("", sysConfigHandler.Update)
			sysConfig.GET("/nodes", sysConfigHandler.GetServerNodes)
			sysConfig.GET("/logs", sysConfigHandler.GetSysLogs)
		}

		// 监控指标
		metrics := api.Group("/metrics")
		{
			metrics.GET("", metricHandler.GetMetrics)
			metrics.GET("/list", metricHandler.GetMetricList)
			metrics.GET("/dashboard", metricHandler.GetDashboardData)
		}
	}
}
