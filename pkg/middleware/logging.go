package middleware

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/utils/traceid"
	"go.uber.org/zap"
)

// LoggingMiddleware 结构化日志中间件
// 记录每个请求的详细信息，包括 TraceID、耗时、请求参数等
func LoggingMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 记录开始时间
		startTime := time.Now()

		// 获取或生成 TraceID
		traceID := c.GetHeader("X-Trace-ID")
		if traceID == "" {
			traceID = traceid.Generate()
		}
		spanID := c.GetHeader("X-Span-ID")

		// 获取请求信息
		method := c.Request.Method
		path := c.Request.URL.Path
		clientIP := c.ClientIP()
		userAgent := c.Request.UserAgent()

		// 创建带上下文的 logger
		requestLogger := logger.WithTraceID(traceID)
		if spanID != "" {
			requestLogger = requestLogger.With(zap.String("span_id", spanID))
		}
		requestLogger = requestLogger.With(
			zap.String("method", method),
			zap.String("path", path),
			zap.String("client_ip", clientIP),
		)

		c.Set("requestLogger", requestLogger)
		c.Next()

		durationMs := float64(time.Since(startTime).Nanoseconds()) / 1e6
		statusCode := c.Writer.Status()
		errorMessage := c.Errors.String()
		fields := []interface{}{
			"status", statusCode,
			"duration_ms", durationMs,
			"user_agent", userAgent,
			"error", errorMessage,
		}

		switch {
		case statusCode >= 500:
			requestLogger.Errorw("request_completed", fields...)
		case statusCode >= 400:
			requestLogger.Warnw("request_completed", fields...)
		default:
			requestLogger.Infow("request_completed", fields...)
		}
	}
}

// RequestLogger 从 context 中获取请求 logger
func RequestLogger(c *gin.Context) *zap.SugaredLogger {
	l, exists := c.Get("requestLogger")
	if !exists {
		return logger.GetLogger()
	}
	sugaredLogger, ok := l.(*zap.SugaredLogger)
	if !ok {
		return logger.GetLogger()
	}
	return sugaredLogger
}
