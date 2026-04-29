package middleware

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/server/config"
	"github.com/mrh30000/go-rpc/pkg/server/flow"
)

const (
	// ContextRateLimiterKey 限流器在 context 中的键名
	ContextRateLimiterKey = "rate_limiter"
)

// RateLimitMiddleware QPS 限流中间件
// 根据用户配置 QPS 限制请求频率
func RateLimitMiddleware(cfgSvc config.Service) gin.HandlerFunc {
	// 创建全局限流器
	limiter := flow.NewRateLimiter(100) // 默认 100 QPS

	return func(c *gin.Context) {
		// 获取当前用户信息
		user, exists := GetCurrentUser(c)

		var qps float64
		var limiterKey string

		if !exists || user == nil {
			// 匿名用户：使用匿名 QPS 限制
			qps = cfgSvc.GetConfigFloat(config.ConfigKeyAnonymousRateLimit, 10.0)
			limiterKey = "anonymous:" + c.ClientIP()
		} else {
			// 注册用户：使用用户 QPS 限制
			qps = user.QuotaQps
			limiterKey = "user:" + strconv.FormatInt(user.ID, 10)
		}

		// 检查是否允许请求
		if !limiter.Allow(limiterKey, qps) {
			c.JSON(http.StatusTooManyRequests, gin.H{
				"code":    429,
				"message": "请求过于频繁，请稍后再试",
			})
			c.Abort()
			return
		}

		// 将限流器存入 context（可选，供 handler 使用）
		c.Set(ContextRateLimiterKey, limiter)

		c.Next()
	}
}

// AnonymousAccessMiddleware 匿名访问控制中间件
// 如果不允许匿名访问且用户未登录，则拒绝请求
func AnonymousAccessMiddleware(cfgSvc config.Service) gin.HandlerFunc {
	return func(c *gin.Context) {
		// 检查是否允许匿名访问
		allowAnonymous := cfgSvc.GetConfigBool(config.ConfigKeyAllowAnonymousAccess, true)

		if !allowAnonymous {
			// 检查用户是否已登录
			user, exists := GetCurrentUser(c)
			if !exists || user == nil {
				c.JSON(http.StatusUnauthorized, gin.H{
					"code":    401,
					"message": "当前不允许匿名访问，请先登录",
				})
				c.Abort()
				return
			}
		}

		c.Next()
	}
}
