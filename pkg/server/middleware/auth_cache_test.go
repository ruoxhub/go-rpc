package middleware

import (
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
)

func TestTokenCacheHitAndMiss(t *testing.T) {
	c := newTokenCache(100*time.Millisecond, 50*time.Millisecond)
	user := &model.UserInfo{ID: 1, UserName: "alice"}

	if _, ok := c.get("tok"); ok {
		t.Fatal("expected miss on empty cache")
	}

	c.set("tok", user)
	got, ok := c.get("tok")
	if !ok || got != user {
		t.Fatalf("expected hit returning user, got ok=%v user=%v", ok, got)
	}
}

func TestTokenCacheTTLExpiry(t *testing.T) {
	c := newTokenCache(40*time.Millisecond, 20*time.Millisecond)
	c.set("tok", &model.UserInfo{ID: 1})

	time.Sleep(80 * time.Millisecond)

	if _, ok := c.get("tok"); ok {
		t.Fatal("expected miss after TTL expiry")
	}
}

func TestTokenCacheNegativeEntry(t *testing.T) {
	c := newTokenCache(time.Second, 30*time.Millisecond)
	c.set("ghost", nil)

	user, ok := c.get("ghost")
	if !ok {
		t.Fatal("expected negative entry to be cached")
	}
	if user != nil {
		t.Fatalf("expected nil user for negative entry, got %v", user)
	}

	time.Sleep(60 * time.Millisecond)
	if _, ok := c.get("ghost"); ok {
		t.Fatal("expected negative entry to expire after negTTL")
	}
}

func TestTokenCacheInvalidate(t *testing.T) {
	c := newTokenCache(time.Second, time.Second)
	c.set("tok", &model.UserInfo{ID: 1})
	c.invalidate("tok")

	if _, ok := c.get("tok"); ok {
		t.Fatal("expected miss after invalidate")
	}
}

func TestTokenCacheSingleflightDedup(t *testing.T) {
	c := newTokenCache(time.Second, time.Second)
	const token = "tok"

	var calls int32
	loader := func() (interface{}, error) {
		atomic.AddInt32(&calls, 1)
		// 模拟慢 DB 查询，让并发请求有机会汇合到同一个 singleflight key 上。
		time.Sleep(50 * time.Millisecond)
		u := &model.UserInfo{ID: 1, UserName: "alice"}
		c.set(token, u)
		return u, nil
	}

	var wg sync.WaitGroup
	const concurrency = 32
	wg.Add(concurrency)
	for i := 0; i < concurrency; i++ {
		go func() {
			defer wg.Done()
			if u, ok := c.get(token); ok && u != nil {
				return
			}
			_, _, _ = c.sf.Do(token, loader)
		}()
	}
	wg.Wait()

	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Fatalf("expected loader to run exactly once via singleflight, got %d", got)
	}
}

func TestLookupGroupConfigCachesPositiveAndNegative(t *testing.T) {
	// 隔离测试缓存：把 default 临时换成新建实例。
	originalCache := defaultGroupCache
	defaultGroupCache = newGroupCache(time.Second, 30*time.Millisecond)
	defer func() { defaultGroupCache = originalCache }()

	var calls int32
	lookup := func(name string) (*model.GroupConfig, error) {
		atomic.AddInt32(&calls, 1)
		if name == "exists" {
			return &model.GroupConfig{GroupName: name, UserName: "owner"}, nil
		}
		return nil, nil
	}

	// 第一次未命中，落到 lookup。
	g, err := LookupGroupConfig("exists", lookup)
	if err != nil || g == nil || g.UserName != "owner" {
		t.Fatalf("unexpected first lookup result: g=%+v err=%v", g, err)
	}
	// 第二次命中缓存，不应再走 lookup。
	g2, err := LookupGroupConfig("exists", lookup)
	if err != nil || g2 == nil {
		t.Fatalf("unexpected cached lookup result: g=%+v err=%v", g2, err)
	}
	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Fatalf("expected 1 lookup call after cache hit, got %d", got)
	}

	// 负缓存：不存在的分组也只查一次。
	if g, err := LookupGroupConfig("missing", lookup); err != nil || g != nil {
		t.Fatalf("expected nil group for missing, got g=%+v err=%v", g, err)
	}
	if g, err := LookupGroupConfig("missing", lookup); err != nil || g != nil {
		t.Fatalf("expected nil group on negative cache hit, got g=%+v err=%v", g, err)
	}
	if got := atomic.LoadInt32(&calls); got != 2 {
		t.Fatalf("expected 2 lookup calls (positive + negative miss), got %d", got)
	}

	// negTTL 后再查 missing 会再走一次 lookup。
	time.Sleep(60 * time.Millisecond)
	if _, err := LookupGroupConfig("missing", lookup); err != nil {
		t.Fatal(err)
	}
	if got := atomic.LoadInt32(&calls); got != 3 {
		t.Fatalf("expected 3 lookup calls after negTTL expiry, got %d", got)
	}
}

func TestLookupGroupConfigDoesNotCacheErrors(t *testing.T) {
	originalCache := defaultGroupCache
	defaultGroupCache = newGroupCache(time.Second, time.Second)
	defer func() { defaultGroupCache = originalCache }()

	var calls int32
	wantErr := errors.New("db down")
	lookup := func(name string) (*model.GroupConfig, error) {
		atomic.AddInt32(&calls, 1)
		return nil, wantErr
	}

	for i := 0; i < 3; i++ {
		if _, err := LookupGroupConfig("any", lookup); !errors.Is(err, wantErr) {
			t.Fatalf("expected wantErr to propagate, got %v", err)
		}
	}
	if got := atomic.LoadInt32(&calls); got != 3 {
		t.Fatalf("expected error path to bypass cache (3 calls), got %d", got)
	}
}

func TestInvalidateGroupClearsEntry(t *testing.T) {
	originalCache := defaultGroupCache
	defaultGroupCache = newGroupCache(time.Second, time.Second)
	defer func() { defaultGroupCache = originalCache }()

	var calls int32
	lookup := func(name string) (*model.GroupConfig, error) {
		atomic.AddInt32(&calls, 1)
		return &model.GroupConfig{GroupName: name}, nil
	}

	if _, err := LookupGroupConfig("g1", lookup); err != nil {
		t.Fatal(err)
	}
	if _, err := LookupGroupConfig("g1", lookup); err != nil {
		t.Fatal(err)
	}
	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Fatalf("expected 1 lookup call before invalidate, got %d", got)
	}

	InvalidateGroup("g1")
	if _, err := LookupGroupConfig("g1", lookup); err != nil {
		t.Fatal(err)
	}
	if got := atomic.LoadInt32(&calls); got != 2 {
		t.Fatalf("expected lookup to re-run after invalidate, got %d calls", got)
	}
}
