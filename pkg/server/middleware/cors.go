// Package middleware provides HTTP middleware for Sekiro server
package middleware

import (
	"net/http"
	"strings"
)

// RouteReplace returns a middleware that replaces route prefix
// If enabled is false, returns a no-op handler
func RouteReplace(enabled bool, prefix string) func(http.Handler) http.Handler {
	if !enabled || prefix == "" {
		return func(next http.Handler) http.Handler {
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				next.ServeHTTP(w, r)
			})
		}
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Replace the prefix
			newPath := strings.TrimPrefix(r.URL.Path, prefix)
			if newPath == r.URL.Path {
				// Prefix not found, pass through
				next.ServeHTTP(w, r)
				return
			}
			if newPath == "" {
				newPath = "/"
			}
			// Modify request path
			r.URL.Path = newPath
			next.ServeHTTP(w, r)
		})
	}
}

// Chain chains multiple middleware together
func Chain(middlewares ...func(http.Handler) http.Handler) func(http.Handler) http.Handler {
	return func(final http.Handler) http.Handler {
		// Apply middleware in reverse order
		for i := len(middlewares) - 1; i >= 0; i-- {
			final = middlewares[i](final)
		}
		return final
	}
}
