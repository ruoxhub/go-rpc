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
