package flow

import (
	"math"
	"sync"
	"sync/atomic"
	"time"

	"golang.org/x/time/rate"
)

const (
	cleanupInterval = 1 * time.Minute
	cleanupTTL      = 10 * time.Minute
	qpsEpsilon      = 1e-6
)

type limiterEntry struct {
	limiter        *rate.Limiter
	qps            float64
	lastActiveUnix int64
}

// RateLimiter QPS 限流器（令牌桶算法）
type RateLimiter struct {
	mu       sync.RWMutex
	limiters map[string]*limiterEntry
	stopChan chan struct{}
}

func NewRateLimiter() *RateLimiter {
	rl := &RateLimiter{
		limiters: make(map[string]*limiterEntry),
		stopChan: make(chan struct{}),
	}
	go rl.startCleanupLoop(cleanupInterval, cleanupTTL)
	return rl
}

// Stop terminates the background cleanup goroutine. Safe to call multiple times.
func (rl *RateLimiter) Stop() {
	select {
	case <-rl.stopChan:
	default:
		close(rl.stopChan)
	}
}

func (rl *RateLimiter) startCleanupLoop(interval, ttl time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	ttlSec := int64(ttl.Seconds())
	for {
		select {
		case <-ticker.C:
			rl.mu.Lock()
			nowUnix := time.Now().Unix()
			for key, entry := range rl.limiters {
				if nowUnix-atomic.LoadInt64(&entry.lastActiveUnix) > ttlSec {
					delete(rl.limiters, key)
				}
			}
			rl.mu.Unlock()
		case <-rl.stopChan:
			return
		}
	}
}

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

	if entry, ok = rl.limiters[key]; ok && sameQPS(entry.qps, qps) {
		atomic.StoreInt64(&entry.lastActiveUnix, time.Now().Unix())
		return entry.limiter
	}

	// Burst = qps*2，允许短时突发
	limiter := rate.NewLimiter(rate.Limit(qps), int(qps*2)+1)
	rl.limiters[key] = &limiterEntry{
		limiter:        limiter,
		qps:            qps,
		lastActiveUnix: time.Now().Unix(),
	}
	return limiter
}

// Allow 检查是否允许请求（key: 用户ID或分组ID）
func (rl *RateLimiter) Allow(key string, qps float64) bool {
	if qps <= 0 {
		return true
	}
	return rl.getLimiter(key, qps).Allow()
}

// Wait 阻塞直到请求被允许
func (rl *RateLimiter) Wait(key string, qps float64) error {
	if qps <= 0 {
		return nil
	}
	return rl.getLimiter(key, qps).Wait(nil)
}

func (rl *RateLimiter) Remove(key string) {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	delete(rl.limiters, key)
}

func (rl *RateLimiter) Cleanup() {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	rl.limiters = make(map[string]*limiterEntry)
}

func sameQPS(a, b float64) bool { return math.Abs(a-b) < qpsEpsilon }
