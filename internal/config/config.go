// Package config provides YAML configuration management for Rpc server
package config

import (
	"os"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"gopkg.in/yaml.v3"
)

// DefaultTimeout is the default timeout in seconds
var DefaultTimeout = 30

// Config holds server configuration
type Config struct {
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
	Alert          AlertConfig    `yaml:"Alert"`         // Alert notification configuration
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

// DefaultConfig returns default configuration
func DefaultConfig() *Config {
	return &Config{
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
	}
}

// Load reads and parses configuration from a YAML file
func Load(path string) (*Config, error) {
	defaultConf := DefaultConfig()

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

	conf := &Config{}
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

	return conf, nil
}

// LoadWithFallback loads configuration from a YAML file with fallback to defaults
func LoadWithFallback(path string) *Config {
	conf, err := Load(path)
	if err != nil {
		logger.Warningf("Using default configuration due to error: %v", err)
		return DefaultConfig()
	}
	return conf
}

// fileExists checks if a file exists
func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// ToYAML converts config to YAML string
func (c *Config) ToYAML() (string, error) {
	data, err := yaml.Marshal(c)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// Save saves configuration to a YAML file
func (c *Config) Save(path string) error {
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
