package handler

import (
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

// 批量路由是静态路径，须与既有 /groups/:groupName 通配符共存；gin 路由冲突会在注册时 panic。
func TestRegisterGroupRoutes_BatchPathsDoNotConflict(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	h := NewGroupHandler(nil, nil, nil)

	assert.NotPanics(t, func() {
		registerGroupRoutes(r.Group("/groups"), h)
	})

	found := map[string]bool{}
	for _, route := range r.Routes() {
		found[route.Method+" "+route.Path] = true
	}
	assert.True(t, found["POST /groups/batch/delete"], "批量删除路由未注册")
	assert.True(t, found["PUT /groups/batch/qps"], "批量 QPS 路由未注册")
}
