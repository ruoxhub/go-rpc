package api

import (
	"net/http"
	"testing"
	"time"
)

func startTestHTTPServer(t *testing.T, server *HTTPServer) {
	t.Helper()

	err := server.Start()
	if err == nil {
		return
	}
	if err.Error() == "listen tcp 127.0.0.1:0: socket: operation not permitted" {
		t.Skipf("当前环境禁止监听本地端口，跳过测试: %v", err)
	}
	t.Fatalf("Failed to start server: %v", err)
}

func TestHTTPServer_Start(t *testing.T) {
	server := NewHTTPServer(&Config{
		Host: "127.0.0.1",
		Port: 0, // 使用随机可用端口
	})

	// 验证服务器可以启动
	startTestHTTPServer(t, server)

	// 验证服务器监听地址
	if server.Addr() == "" {
		t.Fatal("Server address not set")
	}

	// 验证地址格式
	expectedPrefix := "127.0.0.1:"
	if server.Addr()[:len(expectedPrefix)] != expectedPrefix {
		t.Errorf("Expected address prefix %s, got %s", expectedPrefix, server.Addr())
	}

	server.Shutdown()
}

func TestHTTPServer_RegisterHandler(t *testing.T) {
	server := NewHTTPServer(&Config{
		Host: "127.0.0.1",
		Port: 0,
	})

	// 注册测试处理器
	server.RegisterHandler("/test", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	// 验证处理器已注册（通过发送 HTTP 请求）
	startTestHTTPServer(t, server)
	defer server.Shutdown()

	// 等待服务器启动
	time.Sleep(100 * time.Millisecond)

	// 发送请求
	resp, err := http.Get("http://" + server.Addr() + "/test")
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}
}

func TestHTTPServer_Shutdown(t *testing.T) {
	server := NewHTTPServer(&Config{
		Host: "127.0.0.1",
		Port: 0,
	})

	startTestHTTPServer(t, server)

	// 验证可以关闭
	err := server.Shutdown()
	if err != nil {
		t.Errorf("Shutdown failed: %v", err)
	}
}

func TestSameOriginOrNoOrigin(t *testing.T) {
	tests := []struct {
		name   string
		host   string
		origin string
		want   bool
	}{
		{name: "no origin", host: "example.com", origin: "", want: true},
		{name: "same origin http", host: "example.com", origin: "http://example.com", want: true},
		{name: "same origin https", host: "example.com:5612", origin: "https://example.com:5612", want: true},
		{name: "different origin", host: "example.com", origin: "https://evil.example", want: false},
		{name: "invalid origin", host: "example.com", origin: "javascript:alert(1)", want: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req, _ := http.NewRequest(http.MethodGet, "http://"+tt.host+"/business/register", nil)
			req.Host = tt.host
			if tt.origin != "" {
				req.Header.Set("Origin", tt.origin)
			}

			if got := sameOriginOrNoOrigin(req); got != tt.want {
				t.Fatalf("sameOriginOrNoOrigin() = %v, want %v", got, tt.want)
			}
		})
	}
}
