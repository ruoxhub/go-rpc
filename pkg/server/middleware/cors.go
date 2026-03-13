// Package middleware provides HTTP middleware for Sekiro server
package middleware

import (
	"net/http"
	"strings"
)

// CORS returns a CORS middleware handler
// If enabled is false, returns a no-op handler
func CORS(enabled bool) func(http.Handler) http.Handler {
	if !enabled {
		return func(next http.Handler) http.Handler {
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				next.ServeHTTP(w, r)
			})
		}
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			if origin != "" {
				// Allow all origins
				w.Header().Set("Access-Control-Allow-Origin", "*")
				w.Header().Set("Access-Control-Allow-Methods", "POST, GET, OPTIONS, PUT, DELETE, UPDATE")
				w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Length, X-CSRF-Token, Token, session")
				w.Header().Set("Access-Control-Expose-Headers", "Content-Length, Access-Control-Allow-Origin, Access-Control-Allow-Headers")
				w.Header().Set("Access-Control-Allow-Credentials", "true")
			}

			// Handle preflight requests
			if r.Method == "OPTIONS" {
				w.WriteHeader(http.StatusOK)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

// CORSWithConfig returns a CORS middleware with custom configuration
type CORSConfig struct {
	AllowOrigins     []string
	AllowMethods     []string
	AllowHeaders     []string
	ExposeHeaders    []string
	AllowCredentials bool
	MaxAge           int
}

func CORSWithConfig(config CORSConfig) func(http.Handler) http.Handler {
	if len(config.AllowOrigins) == 0 {
		config.AllowOrigins = []string{"*"}
	}
	if len(config.AllowMethods) == 0 {
		config.AllowMethods = []string{"POST", "GET", "OPTIONS", "PUT", "DELETE", "UPDATE"}
	}
	if len(config.AllowHeaders) == 0 {
		config.AllowHeaders = []string{"Authorization", "Content-Length", "X-CSRF-Token", "Token", "session"}
	}
	if len(config.ExposeHeaders) == 0 {
		config.ExposeHeaders = []string{"Content-Length", "Access-Control-Allow-Origin", "Access-Control-Allow-Headers"}
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")

			// Check if origin is allowed
			allowed := false
			for _, o := range config.AllowOrigins {
				if o == "*" || o == origin {
					allowed = true
					break
				}
			}

			if allowed {
				if len(config.AllowOrigins) == 1 && config.AllowOrigins[0] == "*" {
					w.Header().Set("Access-Control-Allow-Origin", "*")
				} else {
					w.Header().Set("Access-Control-Allow-Origin", origin)
				}
				w.Header().Set("Access-Control-Allow-Methods", strings.Join(config.AllowMethods, ", "))
				w.Header().Set("Access-Control-Allow-Headers", strings.Join(config.AllowHeaders, ", "))
				w.Header().Set("Access-Control-Expose-Headers", strings.Join(config.ExposeHeaders, ", "))
				if config.AllowCredentials {
					w.Header().Set("Access-Control-Allow-Credentials", "true")
				}
				if config.MaxAge > 0 {
					w.Header().Set("Access-Control-Max-Age", string(rune(config.MaxAge)))
				}
			}

			// Handle preflight requests
			if r.Method == "OPTIONS" {
				w.WriteHeader(http.StatusOK)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

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
