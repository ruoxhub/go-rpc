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
