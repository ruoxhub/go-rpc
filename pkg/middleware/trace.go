package middleware

import (
	json "github.com/goccy/go-json"
	"sync/atomic"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/utils/traceid"
	"go.uber.org/zap"
)

// TraceRecorder defines the minimal interface for writing trace records.
type TraceRecorder interface {
	Create(record *model.TraceRecord) error
}

// traceRepoPtr stores the injected recorder with atomic safety for concurrent reads.
var traceRepoPtr atomic.Pointer[TraceRecorder]

// SetTraceRecorder injects the TraceRepository used by TraceMiddleware.
// Must be called before the server starts accepting requests.
func SetTraceRecorder(r TraceRecorder) {
	traceRepoPtr.Store(&r)
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

// TraceMiddleware 追踪采集中间件
// 为每个请求生成或提取 TraceID，记录请求追踪信息
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

		// 9. 先快照请求信息，再异步写入追踪记录，避免引用 gin.Context 池化对象
		snapshot := buildTraceSnapshot(c)
		go recordTrace(snapshot, traceID, spanID, startTime, durationMs, status, errorMessage)
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

func recordTrace(snapshot traceSnapshot, traceID, spanID string, startTime time.Time,
	durationMs int64, status, errorMessage string) {

	p := traceRepoPtr.Load()
	if p == nil {
		return
	}

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

	if err := (*p).Create(&record); err != nil {
		logger.Error("写入追踪记录失败", zap.Error(err))
	}
}
