# Config YAML to Env Migration - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate server configuration from `config.yaml` (YAML) to `.env` (environment variables), removing all YAML parsing code and the `gopkg.in/yaml.v3` dependency.

**Architecture:** Keep the existing `ServerConfig` struct unchanged. Replace YAML file loading with environment variable reading via helper functions (`envString`, `envInt`, `envBool`, `envStringSlice`). The `.env` file is loaded into `os.Environ` by the existing `LoadDotEnv()` before config loading. CLI flags override env vars.

**Tech Stack:** Go 1.25, `os.Getenv`, `strconv`, existing `internal/config` package

---

## File Structure

| File | Responsibility |
|---|---|
| `internal/config/env.go` | **Create** — Helper functions for reading typed env vars |
| `internal/config/env_test.go` | **Create** — Tests for env helpers and `LoadServerConfigFromEnv` |
| `internal/config/config.go` | **Modify** — Remove YAML functions, add `LoadServerConfigFromEnv`, change tags, remove `BasicListen`, remove `yaml.v3` import |
| `main.go` | **Modify** — Remove `-c` flag, `ConfigPath`, `loadYAMLConfig`, `applyYAMLConfig`; rewrite `Start()` config loading |
| `main_test.go` | **Modify** — Update `registerRoutes` test (remove nil yamlConfig assumption) |
| `.env.example` | **Modify** — Complete template with all `RPC_*` variables |
| `Dockerfile` | **Modify** — Remove `COPY config.yaml.example` line |
| `docker-compose.yaml` | **Modify** — Remove `config.yaml` volume mount |
| `config.yaml` | **Delete** |
| `config.yaml.example` | **Delete** |

---

### Task 1: Create env helper functions

**Files:**
- Create: `internal/config/env.go`
- Create: `internal/config/env_test.go`

- [ ] **Step 1: Write failing tests for env helpers**

Create `internal/config/env_test.go`:

```go
package config

import (
	"testing"
)

func TestEnvStringReturnsDefaultWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_STRING", "")
	got := envString("TEST_ENV_STRING", "fallback")
	if got != "fallback" {
		t.Fatalf("envString() = %q, want %q", got, "fallback")
	}
}

func TestEnvStringReturnsValueWhenSet(t *testing.T) {
	t.Setenv("TEST_ENV_STRING", "hello")
	got := envString("TEST_ENV_STRING", "fallback")
	if got != "hello" {
		t.Fatalf("envString() = %q, want %q", got, "hello")
	}
}

func TestEnvIntReturnsDefaultWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_INT", "")
	got := envInt("TEST_ENV_INT", 42)
	if got != 42 {
		t.Fatalf("envInt() = %d, want %d", got, 42)
	}
}

func TestEnvIntReturnsValueWhenSet(t *testing.T) {
	t.Setenv("TEST_ENV_INT", "99")
	got := envInt("TEST_ENV_INT", 42)
	if got != 99 {
		t.Fatalf("envInt() = %d, want %d", got, 99)
	}
}

func TestEnvIntReturnsDefaultOnInvalidValue(t *testing.T) {
	t.Setenv("TEST_ENV_INT", "not-a-number")
	got := envInt("TEST_ENV_INT", 42)
	if got != 42 {
		t.Fatalf("envInt() = %d, want %d", got, 42)
	}
}

func TestEnvBoolReturnsDefaultWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_BOOL", "")
	got := envBool("TEST_ENV_BOOL", true)
	if got != true {
		t.Fatalf("envBool() = %v, want %v", got, true)
	}
}

func TestEnvBoolReturnsValueWhenSet(t *testing.T) {
	t.Setenv("TEST_ENV_BOOL", "true")
	got := envBool("TEST_ENV_BOOL", false)
	if got != true {
		t.Fatalf("envBool() = %v, want %v", got, true)
	}
}

func TestEnvBoolReturnsDefaultOnInvalidValue(t *testing.T) {
	t.Setenv("TEST_ENV_BOOL", "maybe")
	got := envBool("TEST_ENV_BOOL", true)
	if got != true {
		t.Fatalf("envBool() = %v, want %v", got, true)
	}
}

func TestEnvStringSliceReturnsDefaultWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_SLICE", "")
	got := envStringSlice("TEST_ENV_SLICE", []string{"a", "b"})
	if len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("envStringSlice() = %v, want [a b]", got)
	}
}

func TestEnvStringSliceParsesCommaDelimited(t *testing.T) {
	t.Setenv("TEST_ENV_SLICE", "x,y,z")
	got := envStringSlice("TEST_ENV_SLICE", nil)
	if len(got) != 3 || got[0] != "x" || got[1] != "y" || got[2] != "z" {
		t.Fatalf("envStringSlice() = %v, want [x y z]", got)
	}
}

func TestEnvStringSliceTrimsWhitespace(t *testing.T) {
	t.Setenv("TEST_ENV_SLICE", " a , b , c ")
	got := envStringSlice("TEST_ENV_SLICE", nil)
	if len(got) != 3 || got[0] != "a" || got[1] != "b" || got[2] != "c" {
		t.Fatalf("envStringSlice() = %v, want [a b c]", got)
	}
}

func TestEnvStringSliceSkipsEmptyEntries(t *testing.T) {
	t.Setenv("TEST_ENV_SLICE", "a,,b")
	got := envStringSlice("TEST_ENV_SLICE", nil)
	if len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("envStringSlice() = %v, want [a b]", got)
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `go test -run TestEnvString -count=1 ./internal/config/...`
Expected: FAIL — `envString` undefined

- [ ] **Step 3: Implement env helpers**

Create `internal/config/env.go`:

```go
package config

import (
	"os"
	"strconv"
	"strings"
)

func envString(key, defaultVal string) string {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return defaultVal
	}
	return v
}

func envInt(key string, defaultVal int) int {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return defaultVal
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return defaultVal
	}
	return n
}

func envBool(key string, defaultVal bool) bool {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return defaultVal
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return defaultVal
	}
	return b
}

func envStringSlice(key string, defaultVal []string) []string {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return defaultVal
	}
	parts := strings.Split(v, ",")
	result := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			result = append(result, p)
		}
	}
	if len(result) == 0 {
		return defaultVal
	}
	return result
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `go test -run "TestEnvString|TestEnvInt|TestEnvBool|TestEnvStringSlice" -count=1 ./internal/config/...`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/config/env.go internal/config/env_test.go
git commit -m "feat(config): add env helper functions for typed environment variable reading"
```

---

### Task 2: Rewrite config.go — remove YAML, add LoadServerConfigFromEnv

**Files:**
- Modify: `internal/config/config.go`
- Create: `internal/config/server_config_test.go`

- [ ] **Step 1: Write failing tests for LoadServerConfigFromEnv**

Create `internal/config/server_config_test.go`:

```go
package config

import (
	"testing"
)

func TestLoadServerConfigFromEnvReturnsDefaultsWhenEmpty(t *testing.T) {
	conf := LoadServerConfigFromEnv()
	defaults := DefaultServerConfig()

	if conf.Host != defaults.Host {
		t.Fatalf("Host = %q, want %q", conf.Host, defaults.Host)
	}
	if conf.Port != defaults.Port {
		t.Fatalf("Port = %d, want %d", conf.Port, defaults.Port)
	}
	if conf.DefaultTimeOut != defaults.DefaultTimeOut {
		t.Fatalf("DefaultTimeOut = %d, want %d", conf.DefaultTimeOut, defaults.DefaultTimeOut)
	}
	if conf.Mode != defaults.Mode {
		t.Fatalf("Mode = %q, want %q", conf.Mode, defaults.Mode)
	}
	if conf.Cors != defaults.Cors {
		t.Fatalf("Cors = %v, want %v", conf.Cors, defaults.Cors)
	}
}

func TestLoadServerConfigFromEnvReadsAllFields(t *testing.T) {
	t.Setenv("RPC_HOST", "10.0.0.1")
	t.Setenv("RPC_PORT", "8080")
	t.Setenv("RPC_MODE", "debug")
	t.Setenv("RPC_TIMEOUT", "60")
	t.Setenv("RPC_CLOSE_LOG", "true")
	t.Setenv("RPC_CLOSE_WEB_LOG", "true")
	t.Setenv("RPC_CORS", "false")
	t.Setenv("RPC_CORS_ORIGINS", "http://a.com,http://b.com")
	t.Setenv("RPC_DISABLE_WEB_ADMIN", "true")
	t.Setenv("RPC_DISABLE_METRICS", "true")
	t.Setenv("RPC_DISABLE_ALERT", "true")
	t.Setenv("RPC_DISABLE_DATABASE", "true")
	t.Setenv("RPC_ROUTE_REPLACE_ENABLE", "true")
	t.Setenv("RPC_ROUTE_REPLACE_PREFIX", "/api")
	t.Setenv("RPC_HTTPS_ENABLE", "true")
	t.Setenv("RPC_HTTPS_LISTEN", ":8443")
	t.Setenv("RPC_HTTPS_PEM_PATH", "/certs/server.pem")
	t.Setenv("RPC_HTTPS_KEY_PATH", "/certs/server.key")
	t.Setenv("RPC_DB_HOST", "db.example.com")
	t.Setenv("RPC_DB_PORT", "5433")
	t.Setenv("RPC_DB_USER", "admin")
	t.Setenv("RPC_DB_PASSWORD", "secret")
	t.Setenv("RPC_DB_NAME", "mydb")
	t.Setenv("RPC_DB_SSL_MODE", "require")
	t.Setenv("RPC_LOG_DIR", "/var/log")
	t.Setenv("RPC_LOG_FILENAME", "app.log")
	t.Setenv("RPC_LOG_MAX_SIZE", "200")
	t.Setenv("RPC_LOG_MAX_BACKUPS", "10")
	t.Setenv("RPC_LOG_MAX_AGE", "60")
	t.Setenv("RPC_LOG_COMPRESS", "false")
	t.Setenv("RPC_SMTP_HOST", "smtp.example.com")
	t.Setenv("RPC_SMTP_PORT", "587")
	t.Setenv("RPC_SMTP_USERNAME", "user")
	t.Setenv("RPC_SMTP_PASSWORD", "pass")
	t.Setenv("RPC_SMTP_FROM", "noreply@example.com")
	t.Setenv("RPC_SMTP_USE_TLS", "true")
	t.Setenv("RPC_PROVIDER_QWEN_TIMEOUT", "300")
	t.Setenv("RPC_PROVIDER_QWEN_LOG_CHUNKS", "true")

	conf := LoadServerConfigFromEnv()

	if conf.Host != "10.0.0.1" {
		t.Fatalf("Host = %q, want %q", conf.Host, "10.0.0.1")
	}
	if conf.Port != 8080 {
		t.Fatalf("Port = %d, want %d", conf.Port, 8080)
	}
	if conf.Mode != "debug" {
		t.Fatalf("Mode = %q, want %q", conf.Mode, "debug")
	}
	if conf.DefaultTimeOut != 60 {
		t.Fatalf("DefaultTimeOut = %d, want %d", conf.DefaultTimeOut, 60)
	}
	if !conf.CloseLog {
		t.Fatal("CloseLog should be true")
	}
	if !conf.CloseWebLog {
		t.Fatal("CloseWebLog should be true")
	}
	if conf.Cors {
		t.Fatal("Cors should be false")
	}
	if len(conf.CorsOrigins) != 2 || conf.CorsOrigins[0] != "http://a.com" {
		t.Fatalf("CorsOrigins = %v", conf.CorsOrigins)
	}
	if !conf.DisableWebAdmin {
		t.Fatal("DisableWebAdmin should be true")
	}
	if !conf.DisableMetrics {
		t.Fatal("DisableMetrics should be true")
	}
	if !conf.DisableAlert {
		t.Fatal("DisableAlert should be true")
	}
	if !conf.DisableDatabase {
		t.Fatal("DisableDatabase should be true")
	}
	if !conf.RouterReplace.IsEnable {
		t.Fatal("RouterReplace.IsEnable should be true")
	}
	if conf.RouterReplace.ReplaceRoute != "/api" {
		t.Fatalf("RouterReplace.ReplaceRoute = %q", conf.RouterReplace.ReplaceRoute)
	}
	if !conf.HttpsServices.IsEnable {
		t.Fatal("HttpsServices.IsEnable should be true")
	}
	if conf.HttpsServices.HttpsListen != ":8443" {
		t.Fatalf("HttpsServices.HttpsListen = %q", conf.HttpsServices.HttpsListen)
	}
	if conf.HttpsServices.PemPath != "/certs/server.pem" {
		t.Fatalf("HttpsServices.PemPath = %q", conf.HttpsServices.PemPath)
	}
	if conf.HttpsServices.KeyPath != "/certs/server.key" {
		t.Fatalf("HttpsServices.KeyPath = %q", conf.HttpsServices.KeyPath)
	}
	if conf.Database.Host != "db.example.com" {
		t.Fatalf("Database.Host = %q", conf.Database.Host)
	}
	if conf.Database.Port != 5433 {
		t.Fatalf("Database.Port = %d", conf.Database.Port)
	}
	if conf.Database.User != "admin" {
		t.Fatalf("Database.User = %q", conf.Database.User)
	}
	if conf.Database.Password != "secret" {
		t.Fatalf("Database.Password = %q", conf.Database.Password)
	}
	if conf.Database.DBName != "mydb" {
		t.Fatalf("Database.DBName = %q", conf.Database.DBName)
	}
	if conf.Database.SSLMode != "require" {
		t.Fatalf("Database.SSLMode = %q", conf.Database.SSLMode)
	}
	if conf.Log.Dir != "/var/log" {
		t.Fatalf("Log.Dir = %q", conf.Log.Dir)
	}
	if conf.Log.Filename != "app.log" {
		t.Fatalf("Log.Filename = %q", conf.Log.Filename)
	}
	if conf.Log.MaxSize != 200 {
		t.Fatalf("Log.MaxSize = %d", conf.Log.MaxSize)
	}
	if conf.Log.MaxBackups != 10 {
		t.Fatalf("Log.MaxBackups = %d", conf.Log.MaxBackups)
	}
	if conf.Log.MaxAge != 60 {
		t.Fatalf("Log.MaxAge = %d", conf.Log.MaxAge)
	}
	if conf.Log.Compress {
		t.Fatal("Log.Compress should be false")
	}
	if conf.Alert.SMTP.Host != "smtp.example.com" {
		t.Fatalf("Alert.SMTP.Host = %q", conf.Alert.SMTP.Host)
	}
	if conf.Alert.SMTP.Port != 587 {
		t.Fatalf("Alert.SMTP.Port = %d", conf.Alert.SMTP.Port)
	}
	if conf.Alert.SMTP.Username != "user" {
		t.Fatalf("Alert.SMTP.Username = %q", conf.Alert.SMTP.Username)
	}
	if conf.Alert.SMTP.Password != "pass" {
		t.Fatalf("Alert.SMTP.Password = %q", conf.Alert.SMTP.Password)
	}
	if conf.Alert.SMTP.From != "noreply@example.com" {
		t.Fatalf("Alert.SMTP.From = %q", conf.Alert.SMTP.From)
	}
	if !conf.Alert.SMTP.UseTLS {
		t.Fatal("Alert.SMTP.UseTLS should be true")
	}
	if conf.Provider.QwenTimeoutSeconds != 300 {
		t.Fatalf("Provider.QwenTimeoutSeconds = %d", conf.Provider.QwenTimeoutSeconds)
	}
	if !conf.Provider.QwenLogChunks {
		t.Fatal("Provider.QwenLogChunks should be true")
	}
}

func TestLoadServerConfigFromEnvSetsGlobalDefaultTimeout(t *testing.T) {
	t.Setenv("RPC_TIMEOUT", "45")
	LoadServerConfigFromEnv()
	if DefaultTimeout != 45 {
		t.Fatalf("DefaultTimeout = %d, want 45", DefaultTimeout)
	}
	DefaultTimeout = 30
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `go test -run "TestLoadServerConfigFromEnv" -count=1 ./internal/config/...`
Expected: FAIL — `LoadServerConfigFromEnv` undefined

- [ ] **Step 3: Rewrite config.go**

Replace the entire contents of `internal/config/config.go` with:

```go
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
	Database        DatabaseConfig `env:"RPC_DB_*"`
	Log             LogConfig      `env:"RPC_LOG_*"`
	Alert           AlertConfig    `env:"RPC_SMTP_*"`
	Provider        ProviderConfig `env:"RPC_PROVIDER_*"`
	CorsOrigins     []string       `env:"RPC_CORS_ORIGINS"`
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
			Host:     "localhost",
			Port:     5432,
			User:     "postgres",
			Password: "postgres",
			DBName:   "sekiro",
			SSLMode:  "disable",
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
			Host:     envString("RPC_DB_HOST", d.Database.Host),
			Port:     envInt("RPC_DB_PORT", d.Database.Port),
			User:     envString("RPC_DB_USER", d.Database.User),
			Password: envString("RPC_DB_PASSWORD", d.Database.Password),
			DBName:   envString("RPC_DB_NAME", d.Database.DBName),
			SSLMode:  envString("RPC_DB_SSL_MODE", d.Database.SSLMode),
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
	}

	// Set global timeout
	DefaultTimeout = conf.DefaultTimeOut

	// Configure logging
	if conf.CloseLog {
		logger.SetEnabled(false)
	}

	return conf
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `go test -run "TestLoadServerConfigFromEnv" -count=1 ./internal/config/...`
Expected: PASS

- [ ] **Step 5: Run all config package tests**

Run: `go test -count=1 ./internal/config/...`
Expected: PASS (existing tests unaffected — they test the AI provider Config, not ServerConfig)

- [ ] **Step 6: Commit**

```bash
git add internal/config/config.go internal/config/server_config_test.go
git commit -m "feat(config): replace YAML loading with LoadServerConfigFromEnv"
```

---

### Task 3: Update main.go — remove YAML loading, wire env loading

**Files:**
- Modify: `main.go`

- [ ] **Step 1: Remove `-c` flag, `ConfigPath`, and related code**

In `main.go`, make these changes:

1. Remove `configPath` variable and `flag.StringVar(&configPath, "c", ...)` from `init()`
2. Remove `ConfigPath` field from `Config` struct
3. Remove `ConfigPath: configPath` from `main()` and `DefaultConfig()`
4. Remove `loadYAMLConfig()` method entirely
5. Remove `applyYAMLConfig()` method entirely
6. Rename `yamlConfig` field on `Server` struct to `serverConfig`

- [ ] **Step 2: Rewrite `Start()` config loading**

Replace the first lines of `Start()` (currently `s.loadYAMLConfig()` + `s.applyYAMLConfig()`) with:

```go
func (s *Server) Start() error {
	config.LoadDotEnv()
	s.serverConfig = config.LoadServerConfigFromEnv()

	// CLI flags override env config
	if s.config.Host != "" {
		s.serverConfig.Host = s.config.Host
	}
	if s.config.Port != 0 {
		s.serverConfig.Port = s.config.Port
	}
	// Apply CLI host/port to the outer Config as well
	s.config.Host = s.serverConfig.Host
	s.config.Port = s.serverConfig.Port

	if s.config.Debug {
		s.serverConfig.Mode = "debug"
	}
```

- [ ] **Step 3: Update all `s.yamlConfig` references to `s.serverConfig`**

Replace every occurrence of `s.yamlConfig` with `s.serverConfig` in the rest of `main.go`. There are references in:
- `Start()` lines 187-301 (disableDB, disableMetrics, disableAlert, database config, SMTP, cors, routeReplace, corsOrigins)
- `registerRoutes()` lines 340-345 (yc fallback)
- `logFileOptions()` function signature parameter name (rename `yc` to `sc`)

- [ ] **Step 4: Update `registerRoutes()` comment**

Replace the comment block:

```go
// registerRoutes can be exercised by tests that bypass NewServer/loadYAMLConfig.
// In that case s.yamlConfig is nil; fall back to the default server config so
// yaml-driven toggles still resolve to a defined value.
```

With:

```go
// registerRoutes can be exercised by tests that bypass NewServer.
// In that case s.serverConfig is nil; fall back to the default server config.
```

- [ ] **Step 5: Build and verify compilation**

Run: `go build ./...`
Expected: Compiles without errors

- [ ] **Step 6: Run existing tests**

Run: `go test ./...`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add main.go
git commit -m "refactor: replace YAML config loading with env-based loading in main.go"
```

---

### Task 4: Update main_test.go

**Files:**
- Modify: `main_test.go`

- [ ] **Step 1: Update TestRegisterRoutesChatCompletionsAndV1NoRoute**

The test creates a `Server` with `yamlConfig: nil` (implicit). After the rename, it now needs `serverConfig: nil` to fall back to `DefaultServerConfig()`. Since `registerRoutes()` already handles this nil case with the `DefaultServerConfig()` fallback, the test should work as-is after the field rename in Task 3.

Verify:

Run: `go test -run TestRegisterRoutesChatCompletionsAndV1NoRoute -count=1 ./...`
Expected: PASS

- [ ] **Step 2: Verify TestNewHTTPConfigPreservesGlobalWriteTimeout**

Run: `go test -run TestNewHTTPConfigPreservesGlobalWriteTimeout -count=1 ./...`
Expected: PASS

- [ ] **Step 3: Commit if any changes were needed**

```bash
git add main_test.go
git commit -m "test: adapt main_test.go for env-based config loading"
```

---

### Task 5: Delete config.yaml, config.yaml.example, and clean up dependencies

**Files:**
- Delete: `config.yaml`
- Delete: `config.yaml.example`

- [ ] **Step 1: Remove config files**

```bash
git rm config.yaml config.yaml.example
```

- [ ] **Step 2: Remove yaml.v3 dependency**

```bash
go mod tidy
```

Verify `gopkg.in/yaml.v3` is no longer in `go.mod`:

Run: `grep yaml go.mod`
Expected: No output (or only unrelated matches)

- [ ] **Step 3: Commit**

```bash
git add config.yaml config.yaml.example go.mod go.sum
git commit -m "chore: remove config.yaml and gopkg.in/yaml.v3 dependency"
```

---

### Task 6: Update Dockerfile and docker-compose.yaml

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yaml`

- [ ] **Step 1: Update Dockerfile**

Remove the line:
```dockerfile
COPY --from=builder /build/config.yaml.example /app/config.yaml
```

- [ ] **Step 2: Update docker-compose.yaml**

Remove the volume mount line:
```yaml
      - ./config.yaml:/app/config.yaml:ro
```

Keep `env_file: - .env` (already present).

- [ ] **Step 3: Commit**

```bash
git add Dockerfile docker-compose.yaml
git commit -m "chore: remove config.yaml references from Docker config"
```

---

### Task 7: Update .env.example with complete template

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Write complete .env.example**

Replace the contents of `.env.example` with:

```env
# ===========================================
# RPC Server Configuration
# ===========================================

# Server
RPC_HOST=0.0.0.0
RPC_PORT=5612
RPC_MODE=release
RPC_TIMEOUT=30

# Logging
RPC_CLOSE_LOG=false
RPC_CLOSE_WEB_LOG=false
RPC_LOG_DIR=logs
RPC_LOG_FILENAME=rpc.log
RPC_LOG_MAX_SIZE=100
RPC_LOG_MAX_BACKUPS=7
RPC_LOG_MAX_AGE=30
RPC_LOG_COMPRESS=true

# CORS
RPC_CORS=true
# RPC_CORS_ORIGINS=http://example.com,http://localhost:3000

# Feature toggles
RPC_DISABLE_WEB_ADMIN=false
RPC_DISABLE_METRICS=false
RPC_DISABLE_ALERT=false
RPC_DISABLE_DATABASE=false

# Route prefix replacement (reverse proxy)
RPC_ROUTE_REPLACE_ENABLE=false
# RPC_ROUTE_REPLACE_PREFIX=/sekiro

# HTTPS (optional)
RPC_HTTPS_ENABLE=false
RPC_HTTPS_LISTEN=:5643
# RPC_HTTPS_PEM_PATH=certs/server.pem
# RPC_HTTPS_KEY_PATH=certs/server.key

# Database (PostgreSQL)
RPC_DB_HOST=localhost
RPC_DB_PORT=5432
RPC_DB_USER=postgres
RPC_DB_PASSWORD=postgres
RPC_DB_NAME=sekiro
RPC_DB_SSL_MODE=disable

# SMTP (alert email)
RPC_SMTP_HOST=localhost
RPC_SMTP_PORT=25
# RPC_SMTP_USERNAME=
# RPC_SMTP_PASSWORD=
RPC_SMTP_FROM=alert@sekiro.local
RPC_SMTP_USE_TLS=false

# Provider (Qwen)
RPC_PROVIDER_QWEN_TIMEOUT=120
RPC_PROVIDER_QWEN_LOG_CHUNKS=false
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: update .env.example with complete RPC_ environment variable template"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run full build**

Run: `go build ./...`
Expected: Compiles without errors

- [ ] **Step 2: Run all tests**

Run: `go test ./...`
Expected: PASS

- [ ] **Step 3: Verify no YAML references remain**

Run: `grep -r "yaml" internal/config/config.go main.go`
Expected: No output

Run: `grep -r "config\.yaml" --include="*.go" --include="*.yaml" --include="*.yml" --include="Dockerfile*" .`
Expected: No output (excluding `.git/`, `docs/`, and `.claude/`)

- [ ] **Step 4: Verify no yaml.v3 import remains**

Run: `grep -r "gopkg.in/yaml" .`
Expected: No output (excluding `.git/`)
