package flow

import (
	"sync"
	"sync/atomic"
	"time"

	"golang.org/x/time/rate"
)

type limiterEntry struct {
	limiter        *rate.Limiter
	qps            float64
	lastActiveUnix int64
}

// RateLimiter QPS 限流器
// 使用令牌桶算法实现
type RateLimiter struct {
	mu         sync.RWMutex
	limiters   map[string]*limiterEntry // key: userID 或 groupID
	defaultQps float64
}

// NewRateLimiter 创建限流器实例
func NewRateLimiter(defaultQps float64) *RateLimiter {
	rl := &RateLimiter{
		limiters:   make(map[string]*limiterEntry),
		defaultQps: defaultQps,
	}

	// 启动后台清理协程：每隔 1 分钟扫描，清除 10 分钟未活跃的限流器
	go rl.startCleanupLoop(1*time.Minute, 10*time.Minute)

	return rl
}

func (rl *RateLimiter) startCleanupLoop(interval, ttl time.Duration) {
	ticker := time.NewTicker(interval)
	for range ticker.C {
		rl.mu.Lock()
		nowUnix := time.Now().Unix()
		ttlSec := int64(ttl.Seconds())
		for key, entry := range rl.limiters {
			lastActive := atomic.LoadInt64(&entry.lastActiveUnix)
			if nowUnix-lastActive > ttlSec {
				delete(rl.limiters, key)
			}
		}
		rl.mu.Unlock()
	}
}

// getLimiter 获取或创建限流器
func (rl *RateLimiter) getLimiter(key string, qps float64) *rate.Limiter {
	rl.mu.RLock()
	entry, ok := rl.limiters[key]
	rl.mu.RUnlock()

	if ok && sameQPS(entry.qps, qps) {
		atomic.StoreInt64(&entry.lastActiveUnix, time.Now().Unix())
		return entry.limiter
	}

	rl.mu.Lock()
	defer rl.mu.Unlock()

	// 双重检查
	if entry, ok = rl.limiters[key]; ok && sameQPS(entry.qps, qps) {
		atomic.StoreInt64(&entry.lastActiveUnix, time.Now().Unix())
		return entry.limiter
	}

	// 创建新的限流器
	// rate.Limit(qps) 表示每秒允许 qps 个请求
	// Burst 设置为 qps 的 2 倍，允许短时突发
	limiter := rate.NewLimiter(rate.Limit(qps), int(qps*2)+1)
	rl.limiters[key] = &limiterEntry{
		limiter:        limiter,
		qps:            qps,
		lastActiveUnix: time.Now().Unix(),
	}

	return limiter
}

// Allow 检查是否允许请求
// key: 用户 ID 或分组 ID
// qps: QPS 限制
func (rl *RateLimiter) Allow(key string, qps float64) bool {
	if qps <= 0 {
		// QPS <= 0 表示无限制
		return true
	}

	limiter := rl.getLimiter(key, qps)
	return limiter.Allow()
}

// Wait 等待直到允许请求（阻塞）
func (rl *RateLimiter) Wait(key string, qps float64) error {
	if qps <= 0 {
		return nil
	}

	limiter := rl.getLimiter(key, qps)
	return limiter.Wait(nil)
}

// Remove 移除限流器（用于清理）
func (rl *RateLimiter) Remove(key string) {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	delete(rl.limiters, key)
}

// Cleanup 清理所有限流器
func (rl *RateLimiter) Cleanup() {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	rl.limiters = make(map[string]*limiterEntry)
}

// SetDefaultQPS 设置默认 QPS
func (rl *RateLimiter) SetDefaultQPS(qps float64) {
	rl.defaultQps = qps
}

// GetDefaultQPS 获取默认 QPS
func (rl *RateLimiter) GetDefaultQPS() float64 {
	return rl.defaultQps
}

func sameQPS(a, b float64) bool {
	const epsilon = 0.000001
	if a > b {
		return a-b < epsilon
	}
	return b-a < epsilon
}
