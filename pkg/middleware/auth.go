package middleware

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"strings"
	"sync/atomic"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// TokenUserLookup defines the minimal interface for token-based user lookup.
type TokenUserLookup interface {
	FindByToken(token string) (*model.UserInfo, error)
}

// tokenUserRepoPtr stores the injected repository with atomic safety for concurrent reads.
var tokenUserRepoPtr atomic.Pointer[TokenUserLookup]

// SetTokenUserRepository injects the UserRepository used by FindUserByToken.
// Must be called before the server starts accepting requests.
func SetTokenUserRepository(r TokenUserLookup) {
	tokenUserRepoPtr.Store(&r)
}

const (
	// ContextUserKey 用户在 context 中的键名
	ContextUserKey = "current_user"
)

// Authenticate 认证中间件处理函数
// 从 Authorization header 中提取 Bearer token，查询用户信息并存入 context
func Authenticate() gin.HandlerFunc {
	return func(c *gin.Context) {
		token := ExtractAuthTokenFromRequest(c, false)
		if token == "" {
			abortJSON(c, http.StatusUnauthorized, "未提供认证信息")
			return
		}

		// 查询用户信息
		user, err := FindUserByToken(token)
		if err != nil {
			abortJSON(c, http.StatusUnauthorized, "无效的认证 token")
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
func OptionalAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		token := ExtractAuthTokenFromRequest(c, false)
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

func ExtractAuthTokenFromRequest(c *gin.Context, allowQueryToken bool) string {
	if token := ExtractBearerToken(c.GetHeader("Authorization")); token != "" {
		return token
	}
	if token := c.GetHeader("token"); token != "" {
		return token
	}
	if allowQueryToken {
		if token := c.Query("token"); token != "" {
			return token
		}
	}
	if token := c.PostForm("token"); token != "" {
		return token
	}
	return ""
}

const wsAuthSubprotocolPrefix = "sekiro-auth."

// ExtractTokenFromSubprotocol 从 Sec-WebSocket-Protocol 请求头中解析隐蔽鉴权 token。
// 约定格式: "sekiro-auth.<token>"。多个子协议以逗号分隔时，返回首个匹配项的 token；
// 无匹配时返回空串。URL 与常见访问日志均不暴露该值，比 query/header 更隐蔽。
func ExtractTokenFromSubprotocol(c *gin.Context) string {
	header := c.GetHeader("Sec-WebSocket-Protocol")
	if header == "" {
		return ""
	}
	for _, raw := range strings.Split(header, ",") {
		proto := strings.TrimSpace(raw)
		if strings.HasPrefix(proto, wsAuthSubprotocolPrefix) && len(proto) > len(wsAuthSubprotocolPrefix) {
			return proto[len(wsAuthSubprotocolPrefix):]
		}
	}
	return ""
}

// IPInList 判断 clientIP 是否命中逗号分隔的 IP/CIDR 白名单。
// 空串或全空白 list 直接返回 false；遇到非法条目跳过继续解析。
func IPInList(clientIP, list string) bool {
	if clientIP == "" {
		return false
	}
	ip := net.ParseIP(clientIP)
	if ip == nil {
		return false
	}
	if ip.IsLoopback() {
		return true
	}
	if strings.TrimSpace(list) == "" {
		return false
	}
	for _, raw := range strings.Split(list, ",") {
		entry := strings.TrimSpace(raw)
		if entry == "" {
			continue
		}
		if strings.Contains(entry, "/") {
			if _, cidr, err := net.ParseCIDR(entry); err == nil && cidr.Contains(ip) {
				return true
			}
			continue
		}
		if entryIP := net.ParseIP(entry); entryIP != nil && entryIP.Equal(ip) {
			return true
		}
	}
	return false
}

// ValidateIPList 校验逗号分隔的 IP/CIDR 白名单：每个非空条目必须是合法 IP 或 CIDR，
// 否则返回首个非法条目的错误。用于 handler 在写入 allowed_ips 前拦截坏数据。
func ValidateIPList(list string) error {
	for _, raw := range strings.Split(list, ",") {
		entry := strings.TrimSpace(raw)
		if entry == "" {
			continue
		}
		if strings.Contains(entry, "/") {
			if _, _, err := net.ParseCIDR(entry); err != nil {
				return fmt.Errorf("invalid CIDR %q", entry)
			}
			continue
		}
		if net.ParseIP(entry) == nil {
			return fmt.Errorf("invalid IP %q", entry)
		}
	}
	return nil
}

// FindUserByToken 根据 api_token 查询用户。
// 命中缓存时直接返回；未命中走 singleflight 合并并发请求，结果（包含 token 不存在）回写缓存。
// DB 错误不缓存，避免短暂故障被放大成持续 30s 的错误窗口。
func FindUserByToken(token string) (*model.UserInfo, error) {
	if token == "" {
		return nil, errors.New("empty token")
	}

	if user, err, hit := typedCacheGet(defaultTokenCache, token); hit {
		return user, err
	}

	v, err, _ := defaultTokenCache.sf.Do(token, func() (interface{}, error) {
		// double-check：等到 singleflight 锁的请求中可能已有先到者填好缓存。
		if user, err, hit := typedCacheGet(defaultTokenCache, token); hit {
			return user, err
		}
		return findUserByTokenFromDB(token)
	})
	if err != nil {
		return nil, err
	}
	return v.(*model.UserInfo), nil
}

// typedCacheGet 统一处理「缓存命中但值为负（nil）」的语义：
//   - 未命中：返回 (_, _, false)
//   - 命中正缓存：返回 (value, nil, true)
//   - 命中负缓存：返回 (nil, errInvalidToken, true)
func typedCacheGet[T any](c *cache[T], key string) (*T, error, bool) {
	v, ok := c.get(key)
	if !ok {
		return nil, nil, false
	}
	if v == nil {
		return nil, errInvalidToken, true
	}
	return v, nil, true
}

var errInvalidToken = errors.New("invalid token")

// findUserByTokenFromDB queries the injected repository; caches positive/negative results.
func findUserByTokenFromDB(token string) (*model.UserInfo, error) {
	p := tokenUserRepoPtr.Load()
	if p == nil {
		return nil, errors.New("user repository not initialized")
	}

	user, err := (*p).FindByToken(token)
	if err != nil {
		return nil, err
	}
	if user == nil {
		defaultTokenCache.set(token, nil)
		return nil, errInvalidToken
	}

	defaultTokenCache.set(token, user)
	return user, nil
}

// GetCurrentUser 从 context 中获取当前用户信息
// 如果在中间件中已经设置了用户信息，可以直接使用此函数获取
func GetCurrentUser(c *gin.Context) (*model.UserInfo, bool) {
	user, ok := c.Get(ContextUserKey)
	if !ok {
		return nil, false
	}
	u, ok := user.(*model.UserInfo)
	return u, ok
}

// RequireAdmin 管理员权限中间件
// 要求当前用户是管理员
func RequireAdmin() gin.HandlerFunc {
	return func(c *gin.Context) {
		user, exists := GetCurrentUser(c)
		if !exists {
			abortJSON(c, http.StatusUnauthorized, "请先登录")
			return
		}

		if !user.IsAdmin {
			abortJSON(c, http.StatusForbidden, "需要管理员权限")
			return
		}

		c.Next()
	}
}

// AuthMiddleware holds dependencies for authentication middleware,
// enabling proper dependency injection without package-level globals.
type AuthMiddleware struct {
	userRepo   TokenUserLookup
	tokenCache *cache[model.UserInfo]
	groupCache *cache[model.GroupConfig]
}

// NewAuthMiddleware creates an AuthMiddleware with explicit dependencies.
func NewAuthMiddleware(userRepo TokenUserLookup, tokenCache *cache[model.UserInfo], groupCache *cache[model.GroupConfig]) *AuthMiddleware {
	return &AuthMiddleware{
		userRepo:   userRepo,
		tokenCache: tokenCache,
		groupCache: groupCache,
	}
}

// Authenticate returns a gin middleware that requires valid authentication.
func (am *AuthMiddleware) Authenticate() gin.HandlerFunc {
	return func(c *gin.Context) {
		token := ExtractAuthTokenFromRequest(c, false)
		if token == "" {
			abortJSON(c, http.StatusUnauthorized, "未提供认证信息")
			return
		}
		user, err := am.findUserByToken(token)
		if err != nil {
			abortJSON(c, http.StatusUnauthorized, "无效的认证 token")
			return
		}
		c.Set(ContextUserKey, user)
		c.Next()
	}
}

// OptionalAuth returns a gin middleware that optionally authenticates.
func (am *AuthMiddleware) OptionalAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		token := ExtractAuthTokenFromRequest(c, false)
		if token == "" {
			c.Next()
			return
		}
		if user, err := am.findUserByToken(token); err == nil {
			c.Set(ContextUserKey, user)
		}
		c.Next()
	}
}

func (am *AuthMiddleware) findUserByToken(token string) (*model.UserInfo, error) {
	if u, ok := am.tokenCache.get(token); ok {
		if u == nil {
			return nil, fmt.Errorf("user not found (cached)")
		}
		return u, nil
	}
	v, err, _ := am.tokenCache.sf.Do(token, func() (interface{}, error) {
		if u, ok := am.tokenCache.get(token); ok {
			return u, nil
		}
		u, err := am.userRepo.FindByToken(token)
		if err != nil {
			return nil, err
		}
		am.tokenCache.set(token, u)
		return u, nil
	})
	if err != nil {
		return nil, err
	}
	if v == nil {
		return nil, fmt.Errorf("user not found")
	}
	return v.(*model.UserInfo), nil
}
