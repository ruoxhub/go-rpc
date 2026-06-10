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
