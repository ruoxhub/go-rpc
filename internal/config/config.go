// Package config provides YAML configuration management for Sekiro server
package config

import (
	"os"

	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
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
		Cors:     true,
		Mode:     "release",
		CloseLog: false,
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
