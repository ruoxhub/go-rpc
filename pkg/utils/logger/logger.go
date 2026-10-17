// Package logger provides logging functionality using zap
package logger

import (
	"os"
	"path/filepath"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"gopkg.in/natefinch/lumberjack.v2"
)

var globalLogger *zap.SugaredLogger

func init() {
	InitLogger(false, nil)
}

// FileOptions configures file-based log output with rotation.
type FileOptions struct {
	Enabled    bool   // Enable file logging
	Dir        string // Log directory, e.g. "logs"
	Filename   string // Log filename, e.g. "sekiro.log"
	MaxSize    int    // Max megabytes per file before rotation
	MaxBackups int    // Max old files to retain
	MaxAge     int    // Max days to retain old files
	Compress   bool   // Gzip old log files
}

// InitLogger initializes the global logger.
//
// Output behavior:
//   - debug=true:  console + file (Tee), level=Debug
//   - debug=false: file only (if fileOpts.Enabled), level=Info
//   - fileOpts==nil or !fileOpts.Enabled: console only (backward compatible)
func InitLogger(debug bool, fileOpts *FileOptions) {
	level := zapcore.InfoLevel
	if debug {
		level = zapcore.DebugLevel
	}

	encoderConfig := zapcore.EncoderConfig{
		TimeKey:        "timestamp",
		LevelKey:       "level",
		NameKey:        "logger",
		CallerKey:      "caller",
		FunctionKey:    zapcore.OmitKey,
		MessageKey:     "message",
		StacktraceKey:  "stacktrace",
		LineEnding:     zapcore.DefaultLineEnding,
		EncodeLevel:    zapcore.LowercaseLevelEncoder,
		EncodeTime:     zapcore.ISO8601TimeEncoder,
		EncodeDuration: zapcore.SecondsDurationEncoder,
		EncodeCaller:   zapcore.ShortCallerEncoder,
	}

	var cores []zapcore.Core

	if fileOpts != nil && fileOpts.Enabled {
		if err := os.MkdirAll(fileOpts.Dir, 0o755); err != nil {
			// If directory creation fails, fall back to console-only
			// to avoid crashing the application.
			consoleWriter := zapcore.AddSync(os.Stderr)
			consoleCore := zapcore.NewCore(
				zapcore.NewJSONEncoder(encoderConfig),
				consoleWriter,
				level,
			)
			logger := zap.New(consoleCore, zap.AddCaller(), zap.AddCallerSkip(1))
			globalLogger = logger.Sugar()
			globalLogger.Errorf("Failed to create log directory %s: %v", fileOpts.Dir, err)
			return
		}

		logPath := filepath.Join(fileOpts.Dir, fileOpts.Filename)
		lj := &lumberjack.Logger{
			Filename:   logPath,
			MaxSize:    fileOpts.MaxSize,
			MaxBackups: fileOpts.MaxBackups,
			MaxAge:     fileOpts.MaxAge,
			Compress:   fileOpts.Compress,
		}
		fileWriter := zapcore.AddSync(lj)
		fileCore := zapcore.NewCore(
			zapcore.NewJSONEncoder(encoderConfig),
			fileWriter,
			level,
		)
		cores = append(cores, fileCore)
	}

	useConsole := debug || fileOpts == nil || !fileOpts.Enabled
	if useConsole {
		consoleWriter := zapcore.AddSync(os.Stdout)
		consoleCore := zapcore.NewCore(
			zapcore.NewJSONEncoder(encoderConfig),
			consoleWriter,
			level,
		)
		cores = append(cores, consoleCore)
	}

	core := zapcore.NewTee(cores...)
	logger := zap.New(core, zap.AddCaller(), zap.AddCallerSkip(1))
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
