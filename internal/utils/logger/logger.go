// Package logger provides logging functionality using zap
package logger

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

var globalLogger *zap.SugaredLogger

func init() {
	InitLogger(false)
}

// InitLogger initializes the global logger
func InitLogger(debug bool) {
	config := zap.NewProductionConfig()

	if debug {
		config.Level = zap.NewAtomicLevelAt(zapcore.DebugLevel)
	} else {
		config.Level = zap.NewAtomicLevelAt(zapcore.InfoLevel)
	}

	// 使用 JSON 编码以支持结构化日志
	config.Encoding = "json"
	config.EncoderConfig.TimeKey = "timestamp"
	config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	config.EncoderConfig.LevelKey = "level"
	config.EncoderConfig.EncodeLevel = zapcore.LowercaseLevelEncoder
	config.EncoderConfig.MessageKey = "message"
	config.EncoderConfig.NameKey = "logger"
	config.EncoderConfig.CallerKey = "caller"
	config.EncoderConfig.FunctionKey = zapcore.OmitKey
	config.EncoderConfig.StacktraceKey = "stacktrace"

	// 输出到 stdout 和 stderr
	config.OutputPaths = []string{"stdout"}
	config.ErrorOutputPaths = []string{"stderr"}

	logger, err := config.Build(zap.AddCaller(), zap.AddCallerSkip(1))
	if err != nil {
		panic(err)
	}

	globalLogger = logger.Sugar()
}

// GetLogger returns the global logger
func GetLogger() *zap.SugaredLogger {
	return globalLogger
}

// Debug logs debug message
func Debug(args ...interface{}) {
	globalLogger.Debug(args...)
}

// Debugf logs debug message with format
func Debugf(format string, args ...interface{}) {
	globalLogger.Debugf(format, args...)
}

// Info logs info message
func Info(args ...interface{}) {
	globalLogger.Info(args...)
}

// Infof logs info message with format
func Infof(format string, args ...interface{}) {
	globalLogger.Infof(format, args...)
}

// Warn logs warning message
func Warn(args ...interface{}) {
	globalLogger.Warn(args...)
}

// Warnf logs warning message with format
func Warnf(format string, args ...interface{}) {
	globalLogger.Warnf(format, args...)
}

// Warningf logs warning message with format (alias for Warnf)
func Warningf(format string, args ...interface{}) {
	globalLogger.Warnf(format, args...)
}

// Error logs error message
func Error(args ...interface{}) {
	globalLogger.Error(args...)
}

// Errorf logs error message with format
func Errorf(format string, args ...interface{}) {
	globalLogger.Errorf(format, args...)
}

// Fatal logs fatal message and exits
func Fatal(args ...interface{}) {
	globalLogger.Fatal(args...)
}

// Fatalf logs fatal message with format and exits
func Fatalf(format string, args ...interface{}) {
	globalLogger.Fatalf(format, args...)
}

// Sync flushes log buffer
func Sync() error {
	return globalLogger.Sync()
}

// NewLogger creates a new logger with fields
func NewLogger(fields ...interface{}) *zap.SugaredLogger {
	return globalLogger.With(fields...)
}

// SetEnabled enables or disables logging
func SetEnabled(enabled bool) {
	if enabled {
		logger, _ := zap.NewProduction()
		globalLogger = logger.Sugar()
	} else {
		// Create a no-op logger
		config := zap.NewProductionConfig()
		config.Level = zap.NewAtomicLevelAt(zapcore.FatalLevel)
		logger, _ := config.Build()
		globalLogger = logger.Sugar()
	}
}

// WithFields returns a logger with the given fields
func WithFields(fields map[string]interface{}) *zap.SugaredLogger {
	var flatFields []interface{}
	for k, v := range fields {
		flatFields = append(flatFields, k, v)
	}
	return globalLogger.With(flatFields...)
}

// Debugw logs debug message with structured fields
func Debugw(msg string, keysAndValues ...interface{}) {
	globalLogger.Debugw(msg, keysAndValues...)
}

// Infow logs info message with structured fields
func Infow(msg string, keysAndValues ...interface{}) {
	globalLogger.Infow(msg, keysAndValues...)
}

// Warnw logs warning message with structured fields
func Warnw(msg string, keysAndValues ...interface{}) {
	globalLogger.Warnw(msg, keysAndValues...)
}

// Errorw logs error message with structured fields
func Errorw(msg string, keysAndValues ...interface{}) {
	globalLogger.Errorw(msg, keysAndValues...)
}

// WithTraceID returns a logger with trace ID
func WithTraceID(traceID string) *zap.SugaredLogger {
	return globalLogger.With(zap.String("trace_id", traceID))
}

// WithSpanID returns a logger with span ID
func WithSpanID(spanID string) *zap.SugaredLogger {
	return globalLogger.With(zap.String("span_id", spanID))
}

// WithGroup returns a logger with group field
func WithGroup(group string) *zap.SugaredLogger {
	return globalLogger.With(zap.String("group", group))
}

// WithDeviceID returns a logger with device ID field
func WithDeviceID(deviceID string) *zap.SugaredLogger {
	return globalLogger.With(zap.String("device_id", deviceID))
}
