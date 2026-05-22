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

// tokenEntry 缓存条目；user == nil 表示负缓存（token 不存在）。
type tokenEntry struct {
	user      *model.UserInfo
	expiresAt time.Time
}

// tokenCache 带 TTL + singleflight 的 token → user 缓存。
type tokenCache struct {
	mu     sync.RWMutex
	items  map[string]tokenEntry
	sf     singleflight.Group
	posTTL time.Duration
	negTTL time.Duration
}

func newTokenCache(positiveTTL, negativeTTL time.Duration) *tokenCache {
	c := &tokenCache{
		items:  make(map[string]tokenEntry),
		posTTL: positiveTTL,
		negTTL: negativeTTL,
	}
	go c.gcLoop()
	return c
}

func (c *tokenCache) get(token string) (*model.UserInfo, bool) {
	c.mu.RLock()
	e, ok := c.items[token]
	c.mu.RUnlock()
	if !ok {
		return nil, false
	}
	if time.Now().After(e.expiresAt) {
		return nil, false
	}
	return e.user, true
}

func (c *tokenCache) set(token string, user *model.UserInfo) {
	ttl := c.posTTL
	if user == nil {
		ttl = c.negTTL
	}
	c.mu.Lock()
	c.items[token] = tokenEntry{user: user, expiresAt: time.Now().Add(ttl)}
	if len(c.items) > cacheSoftCap {
		c.purgeExpiredLocked()
	}
	c.mu.Unlock()
}

func (c *tokenCache) invalidate(token string) {
	if token == "" {
		return
	}
	c.mu.Lock()
	delete(c.items, token)
	c.mu.Unlock()
}

func (c *tokenCache) purgeExpiredLocked() {
	now := time.Now()
	for k, e := range c.items {
		if now.After(e.expiresAt) {
			delete(c.items, k)
		}
	}
}

func (c *tokenCache) gcLoop() {
	t := time.NewTicker(cacheGCInterval)
	defer t.Stop()
	for range t.C {
		c.mu.Lock()
		c.purgeExpiredLocked()
		c.mu.Unlock()
	}
}

// groupEntry 缓存条目；group == nil 表示负缓存（group_config 不存在，视为匿名分组）。
type groupEntry struct {
	group     *model.GroupConfig
	expiresAt time.Time
}

// groupCache 带 TTL + singleflight 的 groupName → GroupConfig 缓存。
type groupCache struct {
	mu     sync.RWMutex
	items  map[string]groupEntry
	sf     singleflight.Group
	posTTL time.Duration
	negTTL time.Duration
}

func newGroupCache(positiveTTL, negativeTTL time.Duration) *groupCache {
	c := &groupCache{
		items:  make(map[string]groupEntry),
		posTTL: positiveTTL,
		negTTL: negativeTTL,
	}
	go c.gcLoop()
	return c
}

func (c *groupCache) get(name string) (*model.GroupConfig, bool) {
	c.mu.RLock()
	e, ok := c.items[name]
	c.mu.RUnlock()
	if !ok {
		return nil, false
	}
	if time.Now().After(e.expiresAt) {
		return nil, false
	}
	return e.group, true
}

func (c *groupCache) set(name string, group *model.GroupConfig) {
	ttl := c.posTTL
	if group == nil {
		ttl = c.negTTL
	}
	c.mu.Lock()
	c.items[name] = groupEntry{group: group, expiresAt: time.Now().Add(ttl)}
	if len(c.items) > cacheSoftCap {
		c.purgeExpiredLocked()
	}
	c.mu.Unlock()
}

func (c *groupCache) invalidate(name string) {
	if name == "" {
		return
	}
	c.mu.Lock()
	delete(c.items, name)
	c.mu.Unlock()
}

func (c *groupCache) purgeExpiredLocked() {
	now := time.Now()
	for k, e := range c.items {
		if now.After(e.expiresAt) {
			delete(c.items, k)
		}
	}
}

func (c *groupCache) gcLoop() {
	t := time.NewTicker(cacheGCInterval)
	defer t.Stop()
	for range t.C {
		c.mu.Lock()
		c.purgeExpiredLocked()
		c.mu.Unlock()
	}
}

// 包级单例。
var (
	defaultTokenCache = newTokenCache(defaultTokenPositiveTTL, defaultTokenNegativeTTL)
	defaultGroupCache = newGroupCache(defaultGroupPositiveTTL, defaultGroupNegativeTTL)
)

// InvalidateToken 显式失效一个 token 的缓存。在用户改密、刷 token、改 IsAdmin/QuotaQps、删除用户时调用。
func InvalidateToken(token string) {
	defaultTokenCache.invalidate(token)
}

// InvalidateGroup 显式失效一个 group_config 的缓存。在 group 创建/删除/改 owner 时调用。
func InvalidateGroup(groupName string) {
	defaultGroupCache.invalidate(groupName)
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
	if v == nil {
		return nil, nil
	}
	return v.(*model.GroupConfig), nil
}
