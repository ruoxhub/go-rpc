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

	config.Encoding = "console"
	config.EncoderConfig.TimeKey = "time"
	config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	config.EncoderConfig.EncodeLevel = zapcore.CapitalColorLevelEncoder

	logger, err := config.Build()
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
