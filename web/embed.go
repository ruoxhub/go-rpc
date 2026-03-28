package webui

import (
	"embed"
	"io/fs"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

// distFiles embeds the built admin panel so the backend can serve it directly.
//
//go:embed dist
var distFiles embed.FS

var (
	distFS    = mustSub(distFiles, "dist")
	assetsFS  = mustSub(distFiles, "dist/assets")
	indexHTML = mustReadFile(distFiles, "dist/index.html")
	rootHTTP  = http.FileServer(http.FS(distFS))
)

func mustSub(fsys fs.FS, dir string) fs.FS {
	sub, err := fs.Sub(fsys, dir)
	if err != nil {
		panic(err)
	}
	return sub
}

func mustReadFile(fsys fs.FS, name string) []byte {
	data, err := fs.ReadFile(fsys, name)
	if err != nil {
		panic(err)
	}
	return data
}

// RegisterRoutes exposes embedded frontend assets on the gin engine.
func RegisterRoutes(engine *gin.Engine) {
	assetsHandler := http.StripPrefix("/assets/", http.FileServer(http.FS(assetsFS)))
	engine.GET("/assets/*filepath", func(c *gin.Context) {
		assetsHandler.ServeHTTP(c.Writer, c.Request)
	})

	rootHandler := http.FileServer(http.FS(distFS))
	engine.GET("/favicon.ico", func(c *gin.Context) {
		rootHandler.ServeHTTP(c.Writer, c.Request)
	})
}

// ServeIndex writes the embedded SPA entrypoint.
func ServeIndex(c *gin.Context) {
	c.Data(http.StatusOK, "text/html; charset=utf-8", indexHTML)
}

// ServePathOrIndex serves an embedded static file when it exists, otherwise
// falls back to the SPA entrypoint for client-side routing.
func ServePathOrIndex(c *gin.Context) {
	name := strings.TrimPrefix(c.Request.URL.Path, "/")
	if name != "" && pathExists(distFS, name) {
		rootHTTP.ServeHTTP(c.Writer, c.Request)
		return
	}

	ServeIndex(c)
}

func pathExists(fsys fs.FS, name string) bool {
	file, err := fsys.Open(name)
	if err != nil {
		return false
	}
	defer file.Close()

	info, err := file.Stat()
	if err != nil {
		return false
	}

	return !info.IsDir()
}
