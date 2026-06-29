package middleware

import (
	json "github.com/goccy/go-json"
	"strings"
	"sync/atomic"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/utils/traceid"
	"go.uber.org/zap"
)

// TraceRecorder defines the minimal interface for writing trace records.
// Create handles single-record inserts (used by non-batched callers);
// CreateBatch handles bulk inserts used by the batched trace pipeline.
type TraceRecorder interface {
	Create(record *model.TraceRecord) error
	CreateBatch(records []*model.TraceRecord) error
}

// traceRecorderPtr stores the active batched recorder. All concurrent reads
// happen via atomic load; writes only occur during startup and shutdown.
var traceRecorderPtr atomic.Pointer[batchedTraceRecorder]

// Batching defaults — tuned so that millisecond-level request bursts
// collapse into a handful of bulk INSERTs instead of one row per request.
const (
	defaultTraceBatchSize    = 100
	defaultTraceFlushInterval = 2 * time.Second
	defaultTraceQueueSize     = 10000
)

// batchedTraceRecorder buffers trace records in a channel and flushes them
// to the underlying repository in bulk INSERTs, on either a size threshold
// or a time interval. High-throughput endpoints no longer pay the cost of
// one INSERT per request.
type batchedTraceRecorder struct {
	repo        TraceRecorder
	queue       chan *model.TraceRecord
	sampleRate  float64
	batchSize   int
	flushEvery  time.Duration
	stopCh      chan struct{}
	stopped     atomic.Bool
	droppedLogs atomic.Uint64
	// seed is an atomic xorshift64 state used by fastRandFloat64. Avoids
	// any mutex contention that math/rand (global or per-instance) would
	// impose on the request hot path.
	seed atomic.Uint64
}

// StartBatchedTraceRecorder starts the background flush worker.
// Safe to call once, before the server begins accepting traffic.
func StartBatchedTraceRecorder(repo TraceRecorder, sampleRate float64, batchSize int) {
	if batchSize <= 0 {
		batchSize = defaultTraceBatchSize
	}
	if sampleRate < 0 {
		sampleRate = 0
	}
	if sampleRate > 1 {
		sampleRate = 1
	}

	rec := &batchedTraceRecorder{
		repo:       repo,
		queue:      make(chan *model.TraceRecord, defaultTraceQueueSize),
		sampleRate: sampleRate,
		batchSize:  batchSize,
		flushEvery: defaultTraceFlushInterval,
		stopCh:     make(chan struct{}),
	}
	// Seed from current time; ensure non-zero (xorshift64 cannot iterate from 0).
	seed := uint64(time.Now().UnixNano())
	if seed == 0 {
		seed = 1
	}
	rec.seed.Store(seed)
	traceRecorderPtr.Store(rec)
	go rec.run()

	logger.Infof("trace recorder started: sample_rate=%.2f batch_size=%d queue=%d",
		sampleRate, batchSize, defaultTraceQueueSize)
}

// fastRandFloat64 returns a pseudo-random float64 in [0,1) using lock-free
// xorshift64* on an atomic seed. Suitable for sampling decisions, NOT for
// cryptography. ~3ns per call vs ~30-60ns for mutex-guarded math/rand.
func (b *batchedTraceRecorder) fastRandFloat64() float64 {
	for {
		old := b.seed.Load()
		x := old
		x ^= x >> 12
		x ^= x << 25
		x ^= x >> 27
		if b.seed.CompareAndSwap(old, x) {
			return float64(x*0x2545F4914F6CDD1D>>11) / float64(1<<53)
		}
	}
}

// shouldTrace samples by rate. Rate <= 0 disables tracing; rate >= 1 records every request.
func (b *batchedTraceRecorder) shouldTrace() bool {
	if b.sampleRate >= 1 {
		return true
	}
	if b.sampleRate <= 0 {
		return false
	}
	return b.fastRandFloat64() < b.sampleRate
}

// SetTraceRecorder wraps the given repository with a batched recorder
// using the default batch size and 100% sampling. Kept for backward
// compatibility; prefer StartBatchedTraceRecorder for production use.
func SetTraceRecorder(r TraceRecorder) {
	StartBatchedTraceRecorder(r, 1.0, defaultTraceBatchSize)
}

// ShutdownTraceRecorder flushes any pending records and stops the worker.
// Safe to call multiple times.
func ShutdownTraceRecorder() {
	rec := traceRecorderPtr.Load()
	if rec == nil {
		return
	}
	rec.stop()
	traceRecorderPtr.Store(nil)
}

func (b *batchedTraceRecorder) run() {
	ticker := time.NewTicker(b.flushEvery)
	defer ticker.Stop()

	batch := make([]*model.TraceRecord, 0, b.batchSize)

	flush := func() {
		if len(batch) == 0 {
			return
		}
		if err := b.repo.CreateBatch(batch); err != nil {
			logger.Error("批量写入追踪记录失败", zap.Int("count", len(batch)), zap.Error(err))
		}
		batch = batch[:0]
	}

	for {
		select {
		case rec, ok := <-b.queue:
			if !ok {
				flush()
				return
			}
			batch = append(batch, rec)
			if len(batch) >= b.batchSize {
				flush()
			}
		case <-ticker.C:
			flush()
		case <-b.stopCh:
			// Drain whatever is left in the channel before exiting,
			// so graceful shutdown does not lose queued records.
			for {
				select {
				case rec, ok := <-b.queue:
					if !ok {
						flush()
						return
					}
					batch = append(batch, rec)
					if len(batch) >= b.batchSize {
						flush()
					}
				default:
					flush()
					return
				}
			}
		}
	}
}

func (b *batchedTraceRecorder) stop() {
	if b.stopped.Swap(true) {
		return
	}
	close(b.stopCh)
}

// enqueue attempts a non-blocking send. Drops silently on a full queue
// to avoid back-pressuring request goroutines.
func (b *batchedTraceRecorder) enqueue(rec *model.TraceRecord) {
	select {
	case b.queue <- rec:
	default:
		// Queue full — drop the record rather than blocking the request path.
		if b.droppedLogs.Add(1)%1000 == 1 {
			logger.Warnf("trace queue saturated, dropped %d records", b.droppedLogs.Load())
		}
	}
}

type traceSnapshot struct {
	ParentSpanID string
	Group        string
	DeviceID     string
	API          string
	Caller       string
	Method       string
	UserAgent    string
	ContentType  string
	StatusCode   int
	UserID       int64
	UserName     string
}

// TraceMiddleware 追踪采集中件
// 为每个请求生成或提取 TraceID,并根据采样率异步批量写入追踪记录
func TraceMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 1. 获取或生成 TraceID
		traceID := c.GetHeader("X-Trace-ID")
		if traceID == "" {
			traceID = traceid.Generate()
		}

		// 2. 生成 SpanID
		spanID := traceid.SpanID()

		// 3. 存入 context
		ctx := traceid.WithTraceID(c.Request.Context(), traceID)
		c.Request = c.Request.WithContext(ctx)

		// 4. 设置响应头
		c.Header("X-Trace-ID", traceID)
		c.Header("X-Span-ID", spanID)

		// 5. 记录开始时间
		startTime := time.Now()

		// 6. 处理请求
		c.Next()

		// 7. 计算耗时
		durationMs := time.Since(startTime).Milliseconds()

		// 8. 确定状态
		status := model.SpanStatusSuccess
		var errorMessage string
		if c.Writer.Status() >= 400 {
			status = model.SpanStatusFailure
			errorMessage = c.Errors.String()
		}

		// 9. 采样决策 + 快照请求信息 + 同步入队（enqueue 为非阻塞 select，
		// 不会反压请求 goroutine；不再 per-request 起 goroutine 以节省调度开销）
		rec := traceRecorderPtr.Load()
		if rec != nil && rec.shouldTrace() {
			snapshot := buildTraceSnapshot(c)
			if !shouldSkipTracePath(snapshot.API) {
				emitTrace(rec, snapshot, traceID, spanID, startTime, durationMs, status, errorMessage)
			}
		}
	}
}

// shouldSkipTracePath returns true for internal/noisy endpoints whose traces
// would only add noise (health checks, trace listing, static assets).
func shouldSkipTracePath(path string) bool {
	switch {
	case strings.HasPrefix(path, "/api/traces"):
		return true
	case strings.HasPrefix(path, "/api/sysconfig/logs"):
		return true
	case strings.HasPrefix(path, "/api/sysconfig/app-logs"):
		return true
	case path == "/health", path == "/healthz", path == "/readyz", path == "/live", path == "/ready":
		return true
	case strings.HasPrefix(path, "/assets/"):
		return true
	case strings.HasPrefix(path, "/favicon.ico"):
		return true
	default:
		return false
	}
}

func buildTraceSnapshot(c *gin.Context) traceSnapshot {
	snapshot := traceSnapshot{
		ParentSpanID: c.GetHeader("X-Parent-Span-ID"),
		Group:        c.Query("group"),
		DeviceID:     c.Query("clientId"),
		API:          c.Request.URL.Path,
		Caller:       c.ClientIP(),
		Method:       c.Request.Method,
		UserAgent:    c.Request.UserAgent(),
		ContentType:  c.ContentType(),
		StatusCode:   c.Writer.Status(),
	}

	if user, exists := GetCurrentUser(c); exists && user != nil {
		snapshot.UserID = user.ID
		snapshot.UserName = user.UserName
	}

	return snapshot
}

// emitTrace builds the TraceRecord on the request goroutine and enqueues it
// for batched insertion. enqueue is a non-blocking send, so this is safe to
// call inline from the middleware without risking request latency.
func emitTrace(rec *batchedTraceRecorder, snapshot traceSnapshot, traceID, spanID string,
	startTime time.Time, durationMs int64, status, errorMessage string) {

	duration := time.Duration(durationMs) * time.Millisecond
	record := model.TraceRecord{
		TraceID:      traceID,
		SpanID:       spanID,
		ParentSpanID: snapshot.ParentSpanID,
		Group:        snapshot.Group,
		DeviceID:     snapshot.DeviceID,
		API:          snapshot.API,
		Caller:       snapshot.Caller,
		StartTime:    startTime,
		EndTime:      startTime.Add(duration),
		DurationMs:   durationMs,
		Status:       status,
		ErrorMessage: errorMessage,
	}

	extraData := map[string]any{
		"method":       snapshot.Method,
		"user_agent":   snapshot.UserAgent,
		"content_type": snapshot.ContentType,
		"status_code":  snapshot.StatusCode,
	}
	if snapshot.UserID > 0 {
		extraData["user_id"] = snapshot.UserID
	}
	if snapshot.UserName != "" {
		extraData["user_name"] = snapshot.UserName
	}

	if data, err := json.Marshal(extraData); err == nil {
		record.ExtraData = string(data)
	} else {
		logger.Error("序列化追踪额外数据失败", zap.Error(err))
	}

	rec.enqueue(&record)
}
