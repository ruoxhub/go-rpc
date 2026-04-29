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

		// 将 logger 存入 context
		c.Set("requestLogger", requestLogger)

		// 处理请求
		c.Next()

		// 计算耗时
		duration := time.Since(startTime)
		durationMs := float64(duration.Nanoseconds()) / 1e6

		// 确定日志级别
		statusCode := c.Writer.Status()
		errorMessage := c.Errors.String()

		// 记录请求日志
		if statusCode >= 500 {
			requestLogger.Errorw("request_completed",
				"status", statusCode,
				"duration_ms", durationMs,
				"user_agent", userAgent,
				"error", errorMessage,
			)
		} else if statusCode >= 400 {
			requestLogger.Warnw("request_completed",
				"status", statusCode,
				"duration_ms", durationMs,
				"user_agent", userAgent,
				"error", errorMessage,
			)
		} else {
			requestLogger.Infow("request_completed",
				"status", statusCode,
				"duration_ms", durationMs,
				"user_agent", userAgent,
				"error", errorMessage,
			)
		}
	}
}

// RequestLogger 从 context 中获取请求 logger
func RequestLogger(c *gin.Context) *zap.SugaredLogger {
	if logger, exists := c.Get("requestLogger"); exists {
		if sugaredLogger, ok := logger.(*zap.SugaredLogger); ok {
			return sugaredLogger
		}
	}
	return logger.GetLogger()
}
