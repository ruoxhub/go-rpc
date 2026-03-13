package api

import (
	"net/http"
	"testing"
	"time"
)

func TestHTTPServer_Start(t *testing.T) {
	server := NewHTTPServer(&Config{
		Host: "127.0.0.1",
		Port: 0, // 使用随机可用端口
	})

	// 验证服务器可以启动
	err := server.Start()
	if err != nil {
		t.Fatalf("Failed to start server: %v", err)
	}

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
	server := NewHTTPServer(DefaultConfig())

	// 注册测试处理器
	server.RegisterHandler("/test", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	// 验证处理器已注册（通过发送 HTTP 请求）
	err := server.Start()
	if err != nil {
		t.Fatalf("Failed to start server: %v", err)
	}
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

	err := server.Start()
	if err != nil {
		t.Fatalf("Failed to start server: %v", err)
	}

	// 验证可以关闭
	err = server.Shutdown()
	if err != nil {
		t.Errorf("Shutdown failed: %v", err)
	}
}
