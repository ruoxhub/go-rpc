package webui

import (
	"io/fs"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestServeIndex(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.GET("/", ServeIndex)

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "<div id=\"root\"></div>") {
		t.Fatalf("expected embedded index.html content")
	}
}

func TestRegisterRoutesServesAssets(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	RegisterRoutes(router)

	assets, err := fs.Glob(assetsFS, "*")
	if err != nil {
		t.Fatalf("failed to list embedded assets: %v", err)
	}
	if len(assets) == 0 {
		t.Fatal("expected embedded assets")
	}

	req := httptest.NewRequest(http.MethodGet, "/assets/"+assets[0], nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected asset to be served, got %d", rec.Code)
	}
}

func TestServePathOrIndexFallsBackToSPA(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.NoRoute(ServePathOrIndex)

	req := httptest.NewRequest(http.MethodGet, "/groups/demo", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "<div id=\"root\"></div>") {
		t.Fatalf("expected SPA index fallback")
	}
}
