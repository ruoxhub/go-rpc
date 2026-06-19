package middleware

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/flow"
)

// LoginRateLimitMiddleware applies a strict per-IP rate limit to login endpoints
// to prevent brute-force password attacks.
func LoginRateLimitMiddleware() gin.HandlerFunc {
	limiter := flow.NewRateLimiter()

	return func(c *gin.Context) {
		key := "login:" + c.ClientIP()
		if !limiter.Allow(key, 5.0) {
			abortJSON(c, http.StatusTooManyRequests, "登录过于频繁，请稍后再试")
			return
		}
		c.Next()
	}
}
