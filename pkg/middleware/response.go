package middleware

import (
	"github.com/gin-gonic/gin"
)

func abortJSON(c *gin.Context, status int, message string) {
	c.JSON(status, gin.H{"code": status, "message": message})
	c.Abort()
}
