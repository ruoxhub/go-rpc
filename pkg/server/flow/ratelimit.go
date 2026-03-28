package flow

import (
	"sync"

	"golang.org/x/time/rate"
)

// RateLimiter QPS 限流器
// 使用令牌桶算法实现
type RateLimiter struct {
	mu       sync.RWMutex
	limiters map[string]*rate.Limiter // key: userID 或 groupID
	defaultQps float64
}

// NewRateLimiter 创建限流器实例
func NewRateLimiter(defaultQps float64) *RateLimiter {
	return &RateLimiter{
		limiters:   make(map[string]*rate.Limiter),
		defaultQps: defaultQps,
	}
}

// getLimiter 获取或创建限流器
func (rl *RateLimiter) getLimiter(key string, qps float64) *rate.Limiter {
	rl.mu.RLock()
	limiter, ok := rl.limiters[key]
	rl.mu.RUnlock()

	if ok {
		return limiter
	}

	rl.mu.Lock()
	defer rl.mu.Unlock()

	// 双重检查
	if limiter, ok := rl.limiters[key]; ok {
		return limiter
	}

	// 创建新的限流器
	// rate.Limit(qps) 表示每秒允许 qps 个请求
	// Burst 设置为 qps 的 2 倍，允许短时突发
	limiter = rate.NewLimiter(rate.Limit(qps), int(qps*2)+1)
	rl.limiters[key] = limiter

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
	rl.limiters = make(map[string]*rate.Limiter)
}

// SetDefaultQPS 设置默认 QPS
func (rl *RateLimiter) SetDefaultQPS(qps float64) {
	rl.defaultQps = qps
}

// GetDefaultQPS 获取默认 QPS
func (rl *RateLimiter) GetDefaultQPS() float64 {
	return rl.defaultQps
}
