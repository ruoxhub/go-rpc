package middleware

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"github.com/sekiro-go/sekiro-go/pkg/utils/traceid"
	"go.uber.org/zap"
)

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

		// 9. 异步写入追踪记录 (不阻塞请求)
		go recordTrace(c, traceID, spanID, startTime, durationMs, status, errorMessage)
	}
}

func recordTrace(c *gin.Context, traceID, spanID string, startTime time.Time,
	durationMs int64, status, errorMessage string) {

	// 检查数据库是否已初始化
	db := database.GetDB()
	if db == nil {
		return
	}

	// 获取父 SpanID（如果有）
	parentSpanID := c.GetHeader("X-Parent-Span-ID")

	record := model.TraceRecord{
		TraceID:      traceID,
		SpanID:       spanID,
		ParentSpanID: parentSpanID,
		Group:        c.Query("group"),
		DeviceID:     c.Query("clientId"),
		API:          c.Request.URL.Path,
		Caller:       c.ClientIP(),
		StartTime:    startTime,
		EndTime:      startTime.Add(time.Duration(durationMs) * time.Millisecond),
		DurationMs:   durationMs,
		Status:       status,
		ErrorMessage: errorMessage,
	}

	// 额外数据
	extraData := map[string]interface{}{
		"method":       c.Request.Method,
		"user_agent":   c.Request.UserAgent(),
		"content_type": c.ContentType(),
		"status_code":  c.Writer.Status(),
	}

	if c.GetInt("userId") > 0 {
		extraData["user_id"] = c.GetInt("userId")
	}
	if userName, exists := c.Get("currentUserName"); exists {
		extraData["user_name"] = userName
	}

	// TODO: 将 extraData 序列化为 JSON 字符串存储
	// 简化实现：暂时不存储 extraData

	if err := database.GetDB().Create(&record).Error; err != nil {
		logger.Error("写入追踪记录失败", zap.Error(err))
	}
}
