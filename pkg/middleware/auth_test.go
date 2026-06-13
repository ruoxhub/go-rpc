package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestExtractAuthTokenFromRequest(t *testing.T) {
	tests := []struct {
		name  string
		setup func(*http.Request)
		want  string
	}{
		{
			name: "authorization bearer",
			setup: func(r *http.Request) {
				r.Header.Set("Authorization", "Bearer token-auth")
			},
			want: "token-auth",
		},
		{
			name: "sekiro token header fallback",
			setup: func(r *http.Request) {
				r.Header.Set("sekiro-token", "token-header")
			},
			want: "token-header",
		},
		{
			name: "query fallback",
			setup: func(r *http.Request) {
				q := r.URL.Query()
				q.Set("sekiro_token", "token-query")
				r.URL.RawQuery = q.Encode()
			},
			want: "token-query",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gin.SetMode(gin.TestMode)
			w := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(w)
			req := httptest.NewRequest(http.MethodGet, "/business/invoke", nil)
			tt.setup(req)
			c.Request = req

			if got := ExtractAuthTokenFromRequest(c); got != tt.want {
				t.Fatalf("ExtractAuthTokenFromRequest() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestExtractAuthTokenFromRequestAuthorizationTakesPriority(t *testing.T) {
	gin.SetMode(gin.TestMode)
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest(http.MethodGet, "/business/invoke?sekiro_token=query-token", nil)
	req.Header.Set("Authorization", "Bearer auth-token")
	req.Header.Set("sekiro-token", "header-token")
	c.Request = req

	if got := ExtractAuthTokenFromRequest(c); got != "auth-token" {
		t.Fatalf("ExtractAuthTokenFromRequest() = %q, want %q", got, "auth-token")
	}
}

func TestIPInList(t *testing.T) {
	tests := []struct {
		name   string
		ip     string
		list   string
		want   bool
	}{
		{"exact match", "10.0.0.5", "10.0.0.5,192.168.1.1", true},
		{"exact miss", "10.0.0.6", "10.0.0.5,192.168.1.1", false},
		{"cidr match", "10.0.0.42", "10.0.0.0/24", true},
		{"cidr miss", "10.0.1.1", "10.0.0.0/24", false},
		{"mixed list", "192.168.1.7", "10.0.0.5, 192.168.1.0/24", true},
		{"whitespace tolerated", "10.0.0.5", " 10.0.0.5 , 192.168.1.1 ", true},
		{"empty list", "10.0.0.5", "", false},
		{"blank list", "10.0.0.5", "   ", false},
		{"empty client ip", "", "10.0.0.5", false},
		{"invalid list entry skipped", "10.0.0.5", "not-an-ip,10.0.0.5", true},
		{"all invalid", "10.0.0.5", "not-an-ip,also-bad", false},
		{"invalid client ip", "garbage", "10.0.0.5", false},
		{"ipv6 exact", "2001:db8::1", "2001:db8::1,10.0.0.5", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := IPInList(tt.ip, tt.list); got != tt.want {
				t.Fatalf("IPInList(%q, %q) = %v, want %v", tt.ip, tt.list, got, tt.want)
			}
		})
	}
}

func TestValidateIPList(t *testing.T) {
	tests := []struct {
		name    string
		list    string
		wantErr bool
	}{
		{"empty", "", false},
		{"blank only", "   ", false},
		{"single ip", "10.0.0.5", false},
		{"single cidr", "10.0.0.0/24", false},
		{"mixed valid", "10.0.0.5, 192.168.0.0/16, 2001:db8::1", false},
		{"whitespace tolerated", " 10.0.0.5 , 192.168.1.0/24 ", false},
		{"trailing comma tolerated", "10.0.0.5,", false},
		{"invalid ip", "not-an-ip", true},
		{"invalid cidr", "10.0.0.0/99", true},
		{"one bad among good", "10.0.0.5, bad, 192.168.1.0/24", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateIPList(tt.list)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ValidateIPList(%q) err=%v, wantErr=%v", tt.list, err, tt.wantErr)
			}
		})
	}
}

func TestExtractTokenFromSubprotocol(t *testing.T) {
	tests := []struct {
		name   string
		header string
		want   string
	}{
		{"no header", "", ""},
		{"single match", "sekiro-auth.abc-token", "abc-token"},
		{"multiple with match", "chat, sekiro-auth.xyz, echo", "xyz"},
		{"no match", "chat, echo", ""},
		{"prefix only no token", "sekiro-auth.", ""},
		{"unrelated prefix", "sekiro-other.tok", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gin.SetMode(gin.TestMode)
			w := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(w)
			req := httptest.NewRequest(http.MethodGet, "/business/register", nil)
			if tt.header != "" {
				req.Header.Set("Sec-WebSocket-Protocol", tt.header)
			}
			c.Request = req
			if got := ExtractTokenFromSubprotocol(c); got != tt.want {
				t.Fatalf("ExtractTokenFromSubprotocol() = %q, want %q", got, tt.want)
			}
		})
	}
}
