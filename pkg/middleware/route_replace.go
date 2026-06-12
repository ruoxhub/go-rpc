package middleware

import (
	"strings"

	"github.com/gin-gonic/gin"
)

// RouteReplaceMiddleware strips a configured URL path prefix before routing.
func RouteReplaceMiddleware(enabled bool, prefix string) gin.HandlerFunc {
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
