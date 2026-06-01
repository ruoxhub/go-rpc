// Package config provides YAML configuration management for Rpc server
package config

import (
	"os"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"gopkg.in/yaml.v3"
)

// DefaultTimeout is the default timeout in seconds
var DefaultTimeout = 30

// ServerConfig holds server configuration loaded from config.yaml.
//
// NOTE: this type was previously named Config but conflicts with the
// credentials-oriented Config defined in config_v2.go (used by the AI provider
// stack). Renamed to ServerConfig to keep both alive in the same package.
type ServerConfig struct {
	BasicListen    string        `yaml:"BasicListen"`    // Listen address, e.g., ":5612"
	Host           string        `yaml:"Host"`           // Listen host, e.g., "0.0.0.0"
	Port           int           `yaml:"Port"`           // Listen port
	HttpsServices  HttpsConfig   `yaml:"HttpsServices"`  // HTTPS configuration
	DefaultTimeOut int           `yaml:"DefaultTimeOut"` // Default timeout in seconds
	CloseLog       bool          `yaml:"CloseLog"`       // Disable logging
	CloseWebLog    bool          `yaml:"CloseWebLog"`    // Disable web access log
	Mode           string        `yaml:"Mode"`           // Running mode (debug, release)
	Cors           bool          `yaml:"Cors"`           // Enable CORS
	RouterReplace  RouterReplace `yaml:"RouterReplace"`  // Route prefix replacement
	DisableWebAdmin bool         `yaml:"DisableWebAdmin"` // Disable web admin panel and /api routes
	DisableMetrics  bool         `yaml:"DisableMetrics"`  // Disable metrics collection
	DisableAlert    bool         `yaml:"DisableAlert"`    // Disable alert evaluation engine
	DisableDatabase bool         `yaml:"DisableDatabase"` // Disable PostgreSQL dependency (DB-less mode)
	Database       DatabaseConfig `yaml:"Database"`      // Database configuration
	Log            LogConfig      `yaml:"Log"`           // File log configuration
	Alert          AlertConfig    `yaml:"Alert"`         // Alert notification configuration
	Provider       ProviderConfig `yaml:"Provider"`      // OpenAI-compatible provider configuration
}

// ProviderConfig holds settings for `/v1/chat/completions` provider adapters.
//
// QwenTimeoutSeconds applies to qwen invocations only. Other providers reuse
// the global DefaultTimeOut.
//
// QwenLogChunks toggles DEBUG logging of every ws chunk byte count and SSE
// event type. Off by default to avoid log explosion under heavy traffic.
type ProviderConfig struct {
	QwenTimeoutSeconds int  `yaml:"QwenTimeoutSeconds"`
	QwenLogChunks      bool `yaml:"QwenLogChunks"`
}

// HttpsConfig holds HTTPS related configuration
type HttpsConfig struct {
	IsEnable    bool   `yaml:"IsEnable"`    // Whether to enable HTTPS
	HttpsListen string `yaml:"HttpsListen"` // HTTPS listen address
	PemPath     string `yaml:"PemPath"`     // PEM certificate path
	KeyPath     string `yaml:"KeyPath"`     // PEM private key path
}

// RouterReplace holds route prefix replacement configuration
type RouterReplace struct {
	IsEnable     bool   `yaml:"IsEnable"`     // Whether to enable route replacement
	ReplaceRoute string `yaml:"ReplaceRoute"` // Route prefix to replace
}

// DatabaseConfig holds database configuration
type DatabaseConfig struct {
	Host     string `yaml:"Host"`     // Database host
	Port     int    `yaml:"Port"`     // Database port
	User     string `yaml:"User"`     // Database user
	Password string `yaml:"Password"` // Database password
	DBName   string `yaml:"DBName"`   // Database name
	SSLMode  string `yaml:"SSLMode"`  // SSL mode
}

// LogConfig holds file log configuration
type LogConfig struct {
	Dir        string `yaml:"Dir"`        // Log directory, default "logs"
	Filename   string `yaml:"Filename"`   // Log filename, default "sekiro.log"
	MaxSize    int    `yaml:"MaxSize"`    // Max megabytes per file before rotation, default 100
	MaxBackups int    `yaml:"MaxBackups"` // Max old files to retain, default 7
	MaxAge     int    `yaml:"MaxAge"`     // Max days to retain old files, default 30
	Compress   bool   `yaml:"Compress"`   // Gzip old log files, default true
}

// AlertConfig holds alert notification configuration
type AlertConfig struct {
	SMTP SMTPConfig `yaml:"SMTP"` // SMTP configuration for email notifications
}

// SMTPConfig holds SMTP server configuration
type SMTPConfig struct {
	Host     string `yaml:"Host"`     // SMTP server host
	Port     int    `yaml:"Port"`     // SMTP server port
	Username string `yaml:"Username"` // SMTP username
	Password string `yaml:"Password"` // SMTP password
	From     string `yaml:"From"`     // Sender email address
	UseTLS   bool   `yaml:"UseTLS"`   // Enable TLS
}

// DefaultServerConfig returns default server configuration
func DefaultServerConfig() *ServerConfig {
	return &ServerConfig{
		BasicListen: ":5612",
		Host:        "0.0.0.0",
		Port:        5612,
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
			Host:     "localhost",
			Port:     5432,
			User:     "postgres",
			Password: "postgres",
			DBName:   "sekiro",
			SSLMode:  "disable",
		},
		Cors:     true,
		Mode:     "release",
		CloseLog: false,
		Log: LogConfig{
			Dir:        "logs",
			Filename:   "sekiro.log",
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
	}
}

// LoadServerConfig reads and parses server configuration from a YAML file
func LoadServerConfig(path string) (*ServerConfig, error) {
	defaultConf := DefaultServerConfig()

	if !fileExists(path) {
		logger.Warningf("Config file not found: %s, using default configuration", path)
		return defaultConf, nil
	}

	file, err := os.Open(path)
	if err != nil {
		logger.Errorf("Failed to open config file: %v", err)
		return defaultConf, err
	}
	defer file.Close()

	conf := &ServerConfig{}
	decoder := yaml.NewDecoder(file)
	if err := decoder.Decode(conf); err != nil {
		logger.Errorf("Failed to parse config file: %v", err)
		return defaultConf, err
	}

	// Merge with defaults for any unset fields
	if conf.BasicListen == "" && conf.Host == "" && conf.Port == 0 {
		conf.BasicListen = defaultConf.BasicListen
		conf.Host = defaultConf.Host
		conf.Port = defaultConf.Port
	}

	if conf.DefaultTimeOut <= 0 {
		conf.DefaultTimeOut = defaultConf.DefaultTimeOut
	}

	// Set global timeout
	DefaultTimeout = conf.DefaultTimeOut

	// Configure logging
	if conf.CloseLog {
		logger.SetEnabled(false)
	}

	// Merge log config defaults for unset fields.
	// Detect whether the Log block was explicitly configured in yaml.
	// If none of the fields carry a non-zero value, the entire block
	// was absent and we should use all defaults (including Compress).
	logBlockConfigured := conf.Log.Dir != "" ||
		conf.Log.Filename != "" ||
		conf.Log.MaxSize > 0 ||
		conf.Log.MaxBackups > 0 ||
		conf.Log.MaxAge > 0

	if conf.Log.Dir == "" {
		conf.Log.Dir = defaultConf.Log.Dir
	}
	if conf.Log.Filename == "" {
		conf.Log.Filename = defaultConf.Log.Filename
	}
	if conf.Log.MaxSize <= 0 {
		conf.Log.MaxSize = defaultConf.Log.MaxSize
	}
	if conf.Log.MaxBackups <= 0 {
		conf.Log.MaxBackups = defaultConf.Log.MaxBackups
	}
	if conf.Log.MaxAge <= 0 {
		conf.Log.MaxAge = defaultConf.Log.MaxAge
	}
	if !logBlockConfigured {
		conf.Log.Compress = defaultConf.Log.Compress
	}

	return conf, nil
}

// LoadServerConfigWithFallback loads server configuration from a YAML file with fallback to defaults
func LoadServerConfigWithFallback(path string) *ServerConfig {
	conf, err := LoadServerConfig(path)
	if err != nil {
		logger.Warningf("Using default configuration due to error: %v", err)
		return DefaultServerConfig()
	}
	return conf
}

// fileExists checks if a file exists
func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// ToYAML converts config to YAML string
func (c *ServerConfig) ToYAML() (string, error) {
	data, err := yaml.Marshal(c)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// Save saves server configuration to a YAML file
func (c *ServerConfig) Save(path string) error {
	data, err := yaml.Marshal(c)
	if err != nil {
		return err
	}

	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()

	_, err = file.Write(data)
	return err
}
