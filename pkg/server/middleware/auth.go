package middleware

import (
	"errors"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/gorm"
)

const (
	// ContextUserKey 用户在 context 中的键名
	ContextUserKey = "current_user"
)

// AuthMiddleware 认证中间件
type AuthMiddleware struct{}

// NewAuthMiddleware 创建认证中间件实例
func NewAuthMiddleware() *AuthMiddleware {
	return &AuthMiddleware{}
}

// Authenticate 认证中间件处理函数
// 从 Authorization header 中提取 Bearer token，查询用户信息并存入 context
func (m *AuthMiddleware) Authenticate() gin.HandlerFunc {
	return func(c *gin.Context) {
		token := ExtractAuthTokenFromRequest(c)
		if token == "" {
			c.JSON(http.StatusUnauthorized, gin.H{
				"code":    401,
				"message": "未提供认证信息",
			})
			c.Abort()
			return
		}

		// 查询用户信息
		user, err := FindUserByToken(token)
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{
				"code":    401,
				"message": "无效的认证 token",
			})
			c.Abort()
			return
		}

		// 将用户信息存入 context
		c.Set(ContextUserKey, user)
		logger.Debugf("用户认证成功：userName=%s, userID=%d", user.UserName, user.ID)

		c.Next()
	}
}

// OptionalAuth 可选认证中间件
// 如果提供了有效的 token 则设置用户信息，否则继续但不设置用户
func (m *AuthMiddleware) OptionalAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		token := ExtractAuthTokenFromRequest(c)
		if token == "" {
			c.Next()
			return
		}
		if user, err := FindUserByToken(token); err == nil {
			c.Set(ContextUserKey, user)
			logger.Debugf("用户认证成功（可选）：userName=%s, userID=%d", user.UserName, user.ID)
		}

		c.Next()
	}
}

func ExtractBearerToken(authHeader string) string {
	if authHeader == "" {
		return ""
	}

	parts := strings.SplitN(authHeader, " ", 2)
	if len(parts) != 2 || parts[0] != "Bearer" {
		return ""
	}

	return parts[1]
}

func ExtractAuthTokenFromRequest(c *gin.Context) string {
	if token := ExtractBearerToken(c.GetHeader("Authorization")); token != "" {
		return token
	}
	if token := c.GetHeader("sekiro-token"); token != "" {
		return token
	}
	if token := c.Query("sekiro_token"); token != "" {
		return token
	}
	if token := c.PostForm("sekiro_token"); token != "" {
		return token
	}
	return ""
}

func FindUserByToken(token string) (*model.UserInfo, error) {
	if token == "" {
		return nil, errors.New("empty token")
	}

	db := database.GetDB()
	if db == nil {
		return nil, errors.New("database not initialized")
	}

	var user model.UserInfo
	if err := db.Where("api_token = ?", token).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("invalid token")
		}
		return nil, err
	}

	return &user, nil
}

// GetCurrentUser 从 context 中获取当前用户信息
// 如果在中间件中已经设置了用户信息，可以直接使用此函数获取
func GetCurrentUser(c *gin.Context) (*model.UserInfo, bool) {
	user, exists := c.Get(ContextUserKey)
	if !exists {
		return nil, false
	}
	u, ok := user.(*model.UserInfo)
	return u, ok
}

// RequireAdmin 管理员权限中间件
// 要求当前用户是管理员
func (m *AuthMiddleware) RequireAdmin() gin.HandlerFunc {
	return func(c *gin.Context) {
		user, exists := GetCurrentUser(c)
		if !exists {
			c.JSON(http.StatusUnauthorized, gin.H{
				"code":    401,
				"message": "请先登录",
			})
			c.Abort()
			return
		}

		if !user.IsAdmin {
			c.JSON(http.StatusForbidden, gin.H{
				"code":    403,
				"message": "需要管理员权限",
			})
			c.Abort()
			return
		}

		c.Next()
	}
}
