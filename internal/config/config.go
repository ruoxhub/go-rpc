package config

import (
	"github.com/mrh30000/go-rpc/internal/utils/logger"
)

// DefaultTimeout is the default timeout in seconds
var DefaultTimeout = 30

// ServerConfig holds server configuration loaded from environment variables.
type ServerConfig struct {
	Host            string         `env:"RPC_HOST"`
	Port            int            `env:"RPC_PORT"`
	HttpsServices   HttpsConfig    `env:"RPC_HTTPS_*"`
	DefaultTimeOut  int            `env:"RPC_TIMEOUT"`
	CloseLog        bool           `env:"RPC_CLOSE_LOG"`
	CloseWebLog     bool           `env:"RPC_CLOSE_WEB_LOG"`
	Mode            string         `env:"RPC_MODE"`
	Cors            bool           `env:"RPC_CORS"`
	RouterReplace   RouterReplace  `env:"RPC_ROUTE_REPLACE_*"`
	DisableWebAdmin bool           `env:"RPC_DISABLE_WEB_ADMIN"`
	DisableMetrics  bool           `env:"RPC_DISABLE_METRICS"`
	DisableAlert    bool           `env:"RPC_DISABLE_ALERT"`
	DisableDatabase bool           `env:"RPC_DISABLE_DATABASE"`
	DisableTrace    bool           `env:"RPC_DISABLE_TRACE"`
	Database        DatabaseConfig `env:"RPC_DB_*"`
	Log             LogConfig      `env:"RPC_LOG_*"`
	Alert           AlertConfig    `env:"RPC_SMTP_*"`
	Provider        ProviderConfig `env:"RPC_PROVIDER_*"`
	CorsOrigins     []string       `env:"RPC_CORS_ORIGINS"`
	TraceSampleRate float64        `env:"RPC_TRACE_SAMPLE_RATE"`
	TraceBatchSize  int            `env:"RPC_TRACE_BATCH_SIZE"`
}

// ProviderConfig holds settings for `/v1/chat/completions` provider adapters.
type ProviderConfig struct {
	QwenTimeoutSeconds int  `env:"RPC_PROVIDER_QWEN_TIMEOUT"`
	QwenLogChunks      bool `env:"RPC_PROVIDER_QWEN_LOG_CHUNKS"`
}

// HttpsConfig holds HTTPS related configuration
type HttpsConfig struct {
	IsEnable    bool   `env:"RPC_HTTPS_ENABLE"`
	HttpsListen string `env:"RPC_HTTPS_LISTEN"`
	PemPath     string `env:"RPC_HTTPS_PEM_PATH"`
	KeyPath     string `env:"RPC_HTTPS_KEY_PATH"`
}

// RouterReplace holds route prefix replacement configuration
type RouterReplace struct {
	IsEnable     bool   `env:"RPC_ROUTE_REPLACE_ENABLE"`
	ReplaceRoute string `env:"RPC_ROUTE_REPLACE_PREFIX"`
}

// DatabaseConfig holds database configuration
type DatabaseConfig struct {
	Host     string `env:"RPC_DB_HOST"`
	Port     int    `env:"RPC_DB_PORT"`
	User     string `env:"RPC_DB_USER"`
	Password string `env:"RPC_DB_PASSWORD"`
	DBName   string `env:"RPC_DB_NAME"`
	SSLMode  string `env:"RPC_DB_SSL_MODE"`

	// Connection pool tuning (applied to the underlying *sql.DB).
	// Defaults are tuned for a mid-traffic service: ~20 concurrent writers
	// with a handful of idle connections kept warm, and a 30-minute max
	// lifetime so Postgres-side state (prepared statements, temp tables) is
	// periodically reclaimed.
	MaxOpenConns    int `env:"RPC_DB_MAX_OPEN_CONNS"`
	MaxIdleConns    int `env:"RPC_DB_MAX_IDLE_CONNS"`
	ConnMaxLifetime int `env:"RPC_DB_CONN_MAX_LIFETIME_SECONDS"`
}

// LogConfig holds file log configuration
type LogConfig struct {
	Dir        string `env:"RPC_LOG_DIR"`
	Filename   string `env:"RPC_LOG_FILENAME"`
	MaxSize    int    `env:"RPC_LOG_MAX_SIZE"`
	MaxBackups int    `env:"RPC_LOG_MAX_BACKUPS"`
	MaxAge     int    `env:"RPC_LOG_MAX_AGE"`
	Compress   bool   `env:"RPC_LOG_COMPRESS"`
}

// AlertConfig holds alert notification configuration
type AlertConfig struct {
	SMTP SMTPConfig `env:"RPC_SMTP_*"`
}

// SMTPConfig holds SMTP server configuration
type SMTPConfig struct {
	Host     string `env:"RPC_SMTP_HOST"`
	Port     int    `env:"RPC_SMTP_PORT"`
	Username string `env:"RPC_SMTP_USERNAME"`
	Password string `env:"RPC_SMTP_PASSWORD"`
	From     string `env:"RPC_SMTP_FROM"`
	UseTLS   bool   `env:"RPC_SMTP_USE_TLS"`
}

// DefaultServerConfig returns default server configuration
func DefaultServerConfig() *ServerConfig {
	return &ServerConfig{
		Host: "0.0.0.0",
		Port: 5612,
		HttpsServices: HttpsConfig{
			IsEnable:    false,
			HttpsListen: ":5643",
		},
		DefaultTimeOut: DefaultTimeout,
		RouterReplace: RouterReplace{
			IsEnable:     false,
			ReplaceRoute: "",
		},
		Database: DatabaseConfig{
			Host:            "localhost",
			Port:            5432,
			User:            "postgres",
			Password:        "postgres",
			DBName:          "sekiro",
			SSLMode:         "disable",
			MaxOpenConns:    25,
			MaxIdleConns:    10,
			ConnMaxLifetime: 1800,
		},
		Cors: true,
		Mode: "release",
		Log: LogConfig{
			Dir:        "logs",
			Filename:   "rpc.log",
			MaxSize:    100,
			MaxBackups: 7,
			MaxAge:     30,
			Compress:   true,
		},
		Alert: AlertConfig{
			SMTP: SMTPConfig{
				Host:     "localhost",
				Port:     25,
				Username: "",
				Password: "",
				From:     "alert@sekiro.local",
				UseTLS:   false,
			},
		},
		Provider: ProviderConfig{
			QwenTimeoutSeconds: 120,
			QwenLogChunks:      false,
		},
		TraceSampleRate: 0.1,
		TraceBatchSize:  100,
	}
}

// LoadServerConfigFromEnv loads server configuration from RPC_* environment variables.
// Unset variables fall back to DefaultServerConfig values.
func LoadServerConfigFromEnv() *ServerConfig {
	d := DefaultServerConfig()

	conf := &ServerConfig{
		Host:            envString("RPC_HOST", d.Host),
		Port:            envInt("RPC_PORT", d.Port),
		DefaultTimeOut:  envInt("RPC_TIMEOUT", d.DefaultTimeOut),
		CloseLog:        envBool("RPC_CLOSE_LOG", d.CloseLog),
		CloseWebLog:     envBool("RPC_CLOSE_WEB_LOG", d.CloseWebLog),
		Mode:            envString("RPC_MODE", d.Mode),
		Cors:            envBool("RPC_CORS", d.Cors),
		DisableWebAdmin: envBool("RPC_DISABLE_WEB_ADMIN", d.DisableWebAdmin),
		DisableMetrics:  envBool("RPC_DISABLE_METRICS", d.DisableMetrics),
		DisableAlert:    envBool("RPC_DISABLE_ALERT", d.DisableAlert),
		DisableDatabase: envBool("RPC_DISABLE_DATABASE", d.DisableDatabase),
		DisableTrace:    envBool("RPC_DISABLE_TRACE", d.DisableTrace),
		CorsOrigins:     envStringSlice("RPC_CORS_ORIGINS", d.CorsOrigins),

		HttpsServices: HttpsConfig{
			IsEnable:    envBool("RPC_HTTPS_ENABLE", d.HttpsServices.IsEnable),
			HttpsListen: envString("RPC_HTTPS_LISTEN", d.HttpsServices.HttpsListen),
			PemPath:     envString("RPC_HTTPS_PEM_PATH", d.HttpsServices.PemPath),
			KeyPath:     envString("RPC_HTTPS_KEY_PATH", d.HttpsServices.KeyPath),
		},

		RouterReplace: RouterReplace{
			IsEnable:     envBool("RPC_ROUTE_REPLACE_ENABLE", d.RouterReplace.IsEnable),
			ReplaceRoute: envString("RPC_ROUTE_REPLACE_PREFIX", d.RouterReplace.ReplaceRoute),
		},

		Database: DatabaseConfig{
			Host:            envString("RPC_DB_HOST", d.Database.Host),
			Port:            envInt("RPC_DB_PORT", d.Database.Port),
			User:            envString("RPC_DB_USER", d.Database.User),
			Password:        envString("RPC_DB_PASSWORD", d.Database.Password),
			DBName:          envString("RPC_DB_NAME", d.Database.DBName),
			SSLMode:         envString("RPC_DB_SSL_MODE", d.Database.SSLMode),
			MaxOpenConns:    envInt("RPC_DB_MAX_OPEN_CONNS", d.Database.MaxOpenConns),
			MaxIdleConns:    envInt("RPC_DB_MAX_IDLE_CONNS", d.Database.MaxIdleConns),
			ConnMaxLifetime: envInt("RPC_DB_CONN_MAX_LIFETIME_SECONDS", d.Database.ConnMaxLifetime),
		},

		Log: LogConfig{
			Dir:        envString("RPC_LOG_DIR", d.Log.Dir),
			Filename:   envString("RPC_LOG_FILENAME", d.Log.Filename),
			MaxSize:    envInt("RPC_LOG_MAX_SIZE", d.Log.MaxSize),
			MaxBackups: envInt("RPC_LOG_MAX_BACKUPS", d.Log.MaxBackups),
			MaxAge:     envInt("RPC_LOG_MAX_AGE", d.Log.MaxAge),
			Compress:   envBool("RPC_LOG_COMPRESS", d.Log.Compress),
		},

		Alert: AlertConfig{
			SMTP: SMTPConfig{
				Host:     envString("RPC_SMTP_HOST", d.Alert.SMTP.Host),
				Port:     envInt("RPC_SMTP_PORT", d.Alert.SMTP.Port),
				Username: envString("RPC_SMTP_USERNAME", d.Alert.SMTP.Username),
				Password: envString("RPC_SMTP_PASSWORD", d.Alert.SMTP.Password),
				From:     envString("RPC_SMTP_FROM", d.Alert.SMTP.From),
				UseTLS:   envBool("RPC_SMTP_USE_TLS", d.Alert.SMTP.UseTLS),
			},
		},

		Provider: ProviderConfig{
			QwenTimeoutSeconds: envInt("RPC_PROVIDER_QWEN_TIMEOUT", d.Provider.QwenTimeoutSeconds),
			QwenLogChunks:      envBool("RPC_PROVIDER_QWEN_LOG_CHUNKS", d.Provider.QwenLogChunks),
		},

		TraceSampleRate: envFloat("RPC_TRACE_SAMPLE_RATE", d.TraceSampleRate),
		TraceBatchSize:  envInt("RPC_TRACE_BATCH_SIZE", d.TraceBatchSize),
	}

	DefaultTimeout = conf.DefaultTimeOut

	if conf.CloseLog {
		logger.SetEnabled(false)
	}

	return conf
}
