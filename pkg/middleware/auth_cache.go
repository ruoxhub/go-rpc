package middleware

import (
	"sync"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
	"golang.org/x/sync/singleflight"
)

const (
	defaultTokenPositiveTTL = 30 * time.Second
	defaultTokenNegativeTTL = 5 * time.Second
	defaultGroupPositiveTTL = 30 * time.Second
	defaultGroupNegativeTTL = 5 * time.Second

	cacheGCInterval = 5 * time.Minute
	cacheSoftCap    = 10000
)

// cache 是带 TTL + singleflight 的 string → *T 通用缓存。
// value == nil 表示负缓存（条目不存在）。
type cache[T any] struct {
	mu       sync.RWMutex
	items    map[string]cacheEntry[T]
	sf       singleflight.Group
	posTTL   time.Duration
	negTTL   time.Duration
	stopChan chan struct{}
	stopOnce sync.Once
}

type cacheEntry[T any] struct {
	value     *T
	expiresAt time.Time
}

func newCache[T any](positiveTTL, negativeTTL time.Duration) *cache[T] {
	c := &cache[T]{
		items:    make(map[string]cacheEntry[T]),
		posTTL:   positiveTTL,
		negTTL:   negativeTTL,
		stopChan: make(chan struct{}),
	}
	go c.gcLoop()
	return c
}

func (c *cache[T]) get(key string) (*T, bool) {
	c.mu.RLock()
	e, ok := c.items[key]
	c.mu.RUnlock()
	if !ok || time.Now().After(e.expiresAt) {
		return nil, false
	}
	return e.value, true
}

func (c *cache[T]) set(key string, value *T) {
	ttl := c.posTTL
	if value == nil {
		ttl = c.negTTL
	}
	c.mu.Lock()
	c.items[key] = cacheEntry[T]{value: value, expiresAt: time.Now().Add(ttl)}
	if len(c.items) > cacheSoftCap {
		c.purgeExpiredLocked()
	}
	c.mu.Unlock()
}

func (c *cache[T]) invalidate(key string) {
	if key == "" {
		return
	}
	c.mu.Lock()
	delete(c.items, key)
	c.mu.Unlock()
}

func (c *cache[T]) clear() {
	c.mu.Lock()
	c.items = make(map[string]cacheEntry[T])
	c.mu.Unlock()
}

func (c *cache[T]) purgeExpiredLocked() {
	now := time.Now()
	for k, e := range c.items {
		if now.After(e.expiresAt) {
			delete(c.items, k)
		}
	}
}

func (c *cache[T]) gcLoop() {
	t := time.NewTicker(cacheGCInterval)
	defer t.Stop()
	for {
		select {
		case <-c.stopChan:
			return
		case <-t.C:
			c.mu.Lock()
			c.purgeExpiredLocked()
			c.mu.Unlock()
		}
	}
}

// Stop 终止该缓存的 GC 协程。可安全多次调用。
func (c *cache[T]) Stop() {
	c.stopOnce.Do(func() { close(c.stopChan) })
}

// ShutdownCaches 停止包级默认缓存（token + group）的 GC 协程，在进程退出时调用以避免协程泄漏。
func ShutdownCaches() {
	defaultTokenCache.Stop()
	defaultGroupCache.Stop()
}

// 包级单例。保留原构造函数名以兼容既有调用与测试。
var (
	defaultTokenCache = newCache[model.UserInfo](defaultTokenPositiveTTL, defaultTokenNegativeTTL)
	defaultGroupCache = newCache[model.GroupConfig](defaultGroupPositiveTTL, defaultGroupNegativeTTL)
)

func newTokenCache(posTTL, negTTL time.Duration) *cache[model.UserInfo] {
	return newCache[model.UserInfo](posTTL, negTTL)
}

func newGroupCache(posTTL, negTTL time.Duration) *cache[model.GroupConfig] {
	return newCache[model.GroupConfig](posTTL, negTTL)
}

// InvalidateToken 显式失效一个 token 的缓存。在用户改密、刷 token、改 IsAdmin/QuotaQps、删除用户时调用。
func InvalidateToken(token string) {
	defaultTokenCache.invalidate(token)
}

// InvalidateGroup 显式失效一个 group_config 的缓存。在 group 创建/删除/改 owner 时调用。
func InvalidateGroup(groupName string) {
	defaultGroupCache.invalidate(groupName)
}

// InvalidateAllTokens 清空所有 token 缓存。在配置变更时调用。
func InvalidateAllTokens() {
	defaultTokenCache.clear()
}

// InvalidateAllGroups 清空所有 group 缓存。在配置变更时调用。
func InvalidateAllGroups() {
	defaultGroupCache.clear()
}

// DefaultTokenCache 返回包级 token 缓存实例（B4 过渡期使用，后续随包级全局一起删除）
func DefaultTokenCache() *cache[model.UserInfo] {
	return defaultTokenCache
}

// DefaultGroupCache 返回包级 group 缓存实例（B4 过渡期使用，后续随包级全局一起删除）
func DefaultGroupCache() *cache[model.GroupConfig] {
	return defaultGroupCache
}

// GroupConfigLookup 是注入式的 GroupConfig 查询函数。实现可走 GORM 直查，也可走 repository。
// 返回 (group=nil, err=nil) 表示 group 不存在（会被负缓存）。
type GroupConfigLookup func(groupName string) (*model.GroupConfig, error)

// LookupGroupConfig 带缓存 + singleflight 的 group_config 查询。
// 命中缓存直接返回；未命中合并并发请求并通过 lookup 加载，结果（包含不存在）回写缓存。
// DB 错误不缓存。
func LookupGroupConfig(groupName string, lookup GroupConfigLookup) (*model.GroupConfig, error) {
	if groupName == "" {
		return nil, nil
	}
	if g, ok := defaultGroupCache.get(groupName); ok {
		return g, nil
	}

	v, err, _ := defaultGroupCache.sf.Do(groupName, func() (interface{}, error) {
		if g, ok := defaultGroupCache.get(groupName); ok {
			return g, nil
		}
		g, err := lookup(groupName)
		if err != nil {
			return nil, err
		}
		defaultGroupCache.set(groupName, g)
		return g, nil
	})
	if err != nil {
		return nil, err
	}
	return v.(*model.GroupConfig), nil
}
