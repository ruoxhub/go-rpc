# Sekiro Go 项目改进计划

**分析日期：** 2026-03-29
**分析范围：** Web 管理界面 API 端点、前端组件调用逻辑

---

## 执行摘要

通过分析浏览器网络请求和前后端代码，发现以下关键问题：

1. **2 个缺失的 API 接口实现**
2. **API 响应格式不统一**
3. **N+1 数据库查询问题**
4. **设备状态判定逻辑分散**

---

## 高优先级改进（建议立即实施）

### 1. 实现缺失的 API 接口

#### 1.1 匿名分组列表接口

**路由：** `GET /sekiro-api/frontend/anonymousGroupList`

**后端实现位置：** `pkg/server/handlers/anonymous.go`

**当前状态：** 已有 `ListOptimized` 方法，但未绑定到 `/sekiro-api/frontend` 路由

**修复方案：**

在 `pkg/server/bootstrap.go` 中添加路由：

```go
frontend := sekiroAPI.Group("/frontend")
{
    frontend.GET("/listGroup", handlers.HandleFrontendListGroup)
    // 新增路由
    frontend.GET("/anonymousGroupList", handlers.HandleFrontendAnonymousGroupList)
}
```

**处理器实现：**

```go
// pkg/server/handlers/login.go 或 anonymous.go
func HandleFrontendAnonymousGroupList(c *gin.Context) {
    // 复用现有的 ListOptimized 方法
    anonymousHandler := NewAnonymousGroupHandler()
    anonymousHandler.ListOptimized(c)
}
```

#### 1.2 分组详情接口

**路由：** `GET /sekiro-api/frontend/groupDetail?groupName=xxx`

**后端实现位置：** `pkg/server/handlers/group.go`

**当前状态：** 已有 `GetDetail` 方法，但未绑定到 `/sekiro-api/frontend` 路由

**修复方案：**

```go
// 在 bootstrap.go 的 frontend 组中添加
frontend.GET("/groupDetail", handlers.HandleFrontendGroupDetail)
```

**处理器实现：**

```go
func HandleFrontendGroupDetail(c *gin.Context) {
    groupName := c.Query("groupName")
    if groupName == "" {
        c.JSON(400, gin.H{"status": -1, "message": "groupName 参数必填"})
        return
    }

    groupHandler := NewGroupHandler()
    // 临时修改 context 参数或调用内部方法
    c.Params = append(c.Params, gin.Param{Key: "groupName", Value: groupName})
    groupHandler.GetDetail(c)
}
```

---

### 2. 统一 API 响应格式

**问题：** 存在两种响应格式（code vs status）

**推荐方案：** 统一使用 `/api/*` 端点的格式

```json
{
  "code": 0,
  "message": "success",
  "data": {...},
  "total": 100
}
```

**实施步骤：**

1. 创建统一响应助手函数（`pkg/server/handlers/response.go`）
2. 逐步迁移 `/sekiro-api/*` 端点使用统一格式
3. 前端axios拦截器适配新格式

---

### 3. 修复 N+1 查询问题

**受影响接口：**
- `GET /sekiro-api/frontend/listGroup`

**当前代码位置：** `pkg/server/handlers/login.go:160-193`

**优化方案：** 参考 `pkg/server/handlers/group.go:44-98` 的实现

```go
func HandleFrontendListGroup(c *gin.Context) {
    db := database.GetDB()
    activeThreshold := time.Now().Add(-5 * time.Minute)

    var stats []struct {
        ID                int64
        GroupName         string
        UserName          string
        QuotaQpsGroup     float64
        QuotaQpsPerDevice float64
        CreateDate        time.Time
        AvailableClients  int64
        DisabledClients   int64
    }

    err := db.Table("group_config gc").
        Select(`
            gc.id, gc.group_name, gc.user_name,
            gc.quota_qps_group, gc.quota_qps_per_device, gc.create_date,
            SUM(CASE WHEN gd.last_active_time > ? THEN 1 ELSE 0 END) as available_clients,
            SUM(CASE WHEN gd.last_active_time <= ? THEN 1 ELSE 0 END) as disabled_clients
        `, activeThreshold, activeThreshold).
        Joins("LEFT JOIN group_device gd ON gc.group_name = gd.group_name").
        Group("gc.id, gc.group_name, gc.user_name, gc.quota_qps_group, gc.quota_qps_per_device, gc.create_date").
        Order("gc.create_date DESC").
        Scan(&stats).Error

    // ... 构建响应
}
```

---

### 4. 统一设备状态判定阈值

**当前常量定义：** `pkg/server/handlers/anonymous.go:64`

```go
const ClientInactiveThreshold = 5 * time.Minute
```

**建议移动到：** `pkg/server/handlers/constants.go`

**全局引用：**

```go
// 所有需要该阈值的地方
activeThreshold := time.Now().Add(-handlers.ClientInactiveThreshold)
```

---

## 中优先级改进（建议近期实施）

### 5. 前端 API 客户端完善

**文件：** `web/src/utils/api.js`

**新增封装：**

```javascript
// 前端兼容 API 封装
export const frontendApi = {
  listGroup: () => apiClient.get('/sekiro-api/frontend/listGroup'),
  anonymousGroupList: () => apiClient.get('/sekiro-api/frontend/anonymousGroupList'),
  groupDetail: (groupName) => apiClient.get('/sekiro-api/frontend/groupDetail', {
    params: { groupName }
  })
}
```

---

### 6. 添加健康检查端点

```go
// GET /health
s.httpServer.Engine().GET("/health", func(c *gin.Context) {
    c.JSON(200, gin.H{
        "status": "healthy",
        "timestamp": time.Now().Format(time.RFC3339),
        "version": "1.0.0",
    })
})
```

---

### 7. 审计日志记录

为以下敏感操作添加审计日志：

- 删除分组
- 删除设备
- 禁用/启用设备
- 删除 Action
- 修改用户 QPS
- 修改系统配置

```go
func logAudit(c *gin.Context, action, resource, detail string) {
    user, _ := middleware.GetCurrentUser(c)
    audit := model.SysLog{
        UserName:  user.UserName,
        Action:    action,
        Resource:  resource,
        Detail:    detail,
        CreateTime: time.Now(),
    }
    database.GetDB().Create(&audit)
}
```

---

## 低优先级改进（长期规划）

### 8. Token 过期和刷新机制

**当前问题：** Token 永不过期

**建议方案：**
- API Token 有效期 24 小时
- Login Token 有效期 7 天
- 添加 Token 刷新端点 `/api/current/token/refresh`（已存在但需检查实现）

---

### 9. Prometheus 指标导出

```go
// 添加 /metrics 端点
s.httpServer.Engine().GET("/metrics", promhttp.Handler().ServeHTTP)
```

**核心指标：**
- `sekiro_clients_total` - 在线客户端总数
- `sekiro_groups_total` - 分组总数
- `sekiro_invokes_total` - RPC 调用总数
- `sekiro_latency_seconds` - RPC 调用延迟直方图

---

### 10. Swagger/OpenAPI 文档

考虑集成 swaggo 生成 API 文档：

```bash
go install github.com/swaggo/swag/cmd/swag@latest
swag init -g cmd/server/main.go
```

---

## 实施优先级

| 优先级 | 任务 | 预计工时 | 影响范围 |
|--------|------|----------|----------|
| P0 | 实现匿名分组列表接口 | 0.5h | 高 |
| P0 | 实现分组详情接口 | 0.5h | 高 |
| P1 | 统一 API 响应格式 | 2h | 中 |
| P1 | 修复 N+1 查询 | 1h | 中 |
| P2 | 统一设备状态阈值 | 0.5h | 低 |
| P2 | 完善前端 API 客户端 | 0.5h | 低 |
| P3 | 健康检查端点 | 0.5h | 低 |
| P3 | 审计日志 | 2h | 中 |

---

## 验证清单

完成改进后，请验证：

- [ ] 匿名分组页面正常加载数据
- [ ] 分组详情页面正常加载数据
- [ ] 所有 API 响应格式一致
- [ ] 数据库查询日志确认无 N+1 问题
- [ ] 前端错误提示正常工作
- [ ] 登录态过期后正确跳转

---

## 相关文件

- `pkg/server/bootstrap.go` - 路由配置
- `pkg/server/handlers/anonymous.go` - 匿名分组处理器
- `pkg/server/handlers/group.go` - 分组处理器
- `pkg/server/handlers/login.go` - 登录和兼容接口处理器
- `web/src/pages/AnonymousGroup.jsx` - 匿名分组页面
- `web/src/pages/GroupDetail.jsx` - 分组详情页面
- `web/src/utils/api.js` - 前端 API 客户端

---

*本文档由 js-reverse 逆向分析生成*
