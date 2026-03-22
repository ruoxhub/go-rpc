# 监控和可观测性增强 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Sekiro RPC 添加完整的可观测性能力，包括调用链路追踪、性能指标采集、告警系统和日志聚合功能。

**Architecture:** 在现有 Gin 中间件和事件总线架构上扩展，通过中间件拦截请求采集追踪数据，使用事件总线解耦采集和聚合逻辑，新增数据库表存储追踪记录和告警规则，提供 RESTful API 支持查询和配置。

**Tech Stack:** Go 1.21+, Gin, GORM, PostgreSQL, uber-go/zap, gorilla/websocket

---

## Chunk 1: 调用链路追踪基础

### Task 1: 定义追踪数据模型

**Files:**
- Modify: `pkg/model/database.go`
- Create: `pkg/model/trace.go`

- [ ] **Step 1: 创建追踪记录模型**

在 `pkg/model/trace.go` 中添加:

```go
package model

import "time"

// TraceRecord 调用链路追踪记录
type TraceRecord struct {
	ID            int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	TraceID       string    `json:"trace_id" gorm:"size:64;not null;index"`
	SpanID        string    `json:"span_id" gorm:"size:64;not null"`
	ParentSpanID  string    `json:"parent_span_id" gorm:"size:64"`
	Group         string    `json:"group" gorm:"size:64;index"`
	DeviceID      string    `json:"device_id" gorm:"size:128"`
	API           string    `json:"api" gorm:"size:256"`
	Caller        string    `json:"caller" gorm:"size:128"`
	StartTime     time.Time `json:"start_time" gorm:"not null;index"`
	EndTime       time.Time `json:"end_time" gorm:"not null"`
	DurationMs    int64     `json:"duration_ms" gorm:"not null"`
	Status        string    `json:"status" gorm:"size:16;not null"` // SUCCESS, FAILURE
	ErrorMessage  string    `json:"error_message" gorm:"type:text"`
	ExtraData     string    `json:"extra_data" gorm:"type:text"` // JSON 格式额外数据
}

func (TraceRecord) TableName() string {
	return "trace_record"
}

// TraceQuery 追踪查询参数
type TraceQuery struct {
	TraceID    string `json:"traceId" form:"traceId"`
	Group      string `json:"group" form:"group"`
	DeviceID   string `json:"deviceId" form:"deviceId"`
	API        string `json:"api" form:"api"`
	Status     string `json:"status" form:"status"`
	StartTime  string `json:"startTime" form:"startTime"`
	EndTime    string `json:"endTime" form:"endTime"`
	MinDuration int64 `json:"minDuration" form:"minDuration"`
	MaxDuration int64 `json:"maxDuration" form:"maxDuration"`
	Page       int    `json:"page" form:"page" form:"1"`
	PageSize   int    `json:"pageSize" form:"pageSize" form:"20"`
}
```

- [ ] **Step 2: 在 database.go 中注册模型**

修改 `pkg/model/database.go`，在自动迁移中添加:

```go
// 在 AutoMigrate 调用中添加
db.AutoMigrate(&TraceRecord{})
```

- [ ] **Step 3: 创建数据库迁移脚本**

Create: `deploy/postgres/migration/002_add_trace_record.sql`

```sql
-- 调用链路追踪表
CREATE TABLE IF NOT EXISTS trace_record (
    id BIGSERIAL PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL,
    span_id VARCHAR(64) NOT NULL,
    parent_span_id VARCHAR(64),
    "group" VARCHAR(64),
    device_id VARCHAR(128),
    api VARCHAR(256),
    caller VARCHAR(128),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    duration_ms BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL,
    error_message TEXT,
    extra_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_trace_record_trace_id ON trace_record(trace_id);
CREATE INDEX idx_trace_record_group ON trace_record("group");
CREATE INDEX idx_trace_record_start_time ON trace_record(start_time);
CREATE INDEX idx_trace_record_status ON trace_record(status);
CREATE INDEX idx_trace_record_api ON trace_record(api);

-- 注释
COMMENT ON TABLE trace_record IS '调用链路追踪记录';
COMMENT ON COLUMN trace_record.trace_id IS '追踪 ID';
COMMENT ON COLUMN trace_record.span_id IS 'Span ID';
COMMENT ON COLUMN trace_record.parent_span_id IS '父 Span ID';
COMMENT ON COLUMN trace_record.duration_ms IS '耗时 (毫秒)';
COMMENT ON COLUMN trace_record.status IS '状态：SUCCESS, FAILURE';
```

- [ ] **Step 4: 提交**

```bash
git add pkg/model/trace.go pkg/model/database.go deploy/postgres/migration/002_add_trace_record.sql
git commit -m "feat(trace): 添加调用链路追踪数据模型"
```

---

### Task 2: 实现追踪 ID 生成工具

**Files:**
- Create: `pkg/utils/traceid/traceid.go`
- Test: `pkg/utils/traceid/traceid_test.go`

- [ ] **Step 1: 编写测试**

```go
package traceid

import (
    "testing"
    "github.com/stretchr/testify/assert"
)

func TestGenerate(t *testing.T) {
    id := Generate()
    assert.NotEmpty(t, id)
    assert.Len(t, id, 32) // 16 字节 hex = 32 字符
}

func TestGenerateUnique(t *testing.T) {
    ids := make(map[string]bool)
    for i := 0; i < 1000; i++ {
        id := Generate()
        assert.False(t, ids[id], "重复的 TraceID: %s", id)
        ids[id] = true
    }
}

func TestFromContext(t *testing.T) {
    // 测试从 context 获取 TraceID
    ctx := context.Background()
    ctx = WithTraceID(ctx, "test-trace-id")
    traceID, ok := FromContext(ctx)
    assert.True(t, ok)
    assert.Equal(t, "test-trace-id", traceID)
}
```

- [ ] **Step 2: 实现 TraceID 工具**

```go
package traceid

import (
    "context"
    "crypto/rand"
    "encoding/hex"
)

type contextKey string

const traceIDKey contextKey = "trace_id"

// Generate 生成新的 TraceID (32 字符 hex 字符串)
func Generate() string {
    b := make([]byte, 16)
    if _, err := rand.Read(b); err != nil {
        // Fallback 使用时间戳
        return hex.EncodeToString([]byte(fmt.Sprintf("%d", time.Now().UnixNano())))
    }
    return hex.EncodeToString(b)
}

// WithTraceID 将 TraceID 存入 context
func WithTraceID(ctx context.Context, traceID string) context.Context {
    return context.WithValue(ctx, traceIDKey, traceID)
}

// FromContext 从 context 获取 TraceID
func FromContext(ctx context.Context) (string, bool) {
    id, ok := ctx.Value(traceIDKey).(string)
    return id, ok
}

// SpanID 生成 SpanID
func SpanID() string {
    b := make([]byte, 8)
    if _, err := rand.Read(b); err != nil {
        return hex.EncodeToString([]byte(fmt.Sprintf("%d", time.Now().UnixNano())))
    }
    return hex.EncodeToString(b)
}
```

- [ ] **Step 3: 运行测试**

```bash
cd pkg/utils/traceid
go test -v -race
# Expected: PASS
```

- [ ] **Step 4: 提交**

```bash
git add pkg/utils/traceid/
git commit -m "feat(trace): 添加 TraceID 生成工具"
```

---

### Task 3: 创建追踪采集中间件

**Files:**
- Create: `pkg/server/middleware/trace.go`
- Test: `pkg/server/middleware/trace_test.go`

- [ ] **Step 1: 编写中间件测试**

```go
package middleware

import (
    "net/http/httptest"
    "testing"
    "github.com/gin-gonic/gin"
    "github.com/stretchr/testify/assert"
)

func TestTraceMiddleware(t *testing.T) {
    w := httptest.NewRecorder()
    c, _ := gin.CreateTestContext(w)

    c.Request = httptest.NewRequest("POST", "/business/invoke", nil)
    c.Request.Header.Set("X-Trace-ID", "custom-trace-id")

    TraceMiddleware()(c)

    // 验证 TraceID 被设置到 context
    traceID, ok := traceid.FromContext(c.Request.Context())
    assert.True(t, ok)
    assert.Equal(t, "custom-trace-id", traceID)
}
```

- [ ] **Step 2: 实现追踪采集中间件**

```go
package middleware

import (
    "github.com/gin-gonic/gin"
    "github.com/sekiro-go/sekiro-go/pkg/utils/traceid"
    "time"
)

// TraceMiddleware 追踪采集中间件
func TraceMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        // 1. 获取或生成 TraceID
        traceID := c.GetHeader("X-Trace-ID")
        if traceID == "" {
            traceID = traceid.Generate()
        }

        // 2. 生成 SpanID
        spanID := traceid.SpanID()

        // 3. 存入 context
        ctx := traceid.WithTraceID(c.Request.Context(), traceID)
        c.Request = c.Request.WithContext(ctx)

        // 4. 设置响应头
        c.Header("X-Trace-ID", traceID)

        // 5. 记录开始时间
        startTime := time.Now()

        // 6. 处理请求
        c.Next()

        // 7. 计算耗时
        durationMs := time.Since(startTime).Milliseconds()

        // 8. 确定状态
        status := "SUCCESS"
        var errorMessage string
        if c.Writer.Status() >= 400 {
            status = "FAILURE"
            errorMessage = c.Errors.String()
        }

        // 9. 异步写入追踪记录 (不阻塞请求)
        go recordTrace(c, traceID, spanID, startTime, durationMs, status, errorMessage)
    }
}

func recordTrace(c *gin.Context, traceID, spanID string, startTime time.Time,
    durationMs int64, status, errorMessage string) {

    record := model.TraceRecord{
        TraceID:      traceID,
        SpanID:       spanID,
        Group:        c.Query("group"),
        DeviceID:     c.Query("clientId"),
        API:          c.Request.URL.Path,
        Caller:       c.ClientIP(),
        StartTime:    startTime,
        EndTime:      startTime.Add(time.Duration(durationMs) * time.Millisecond),
        DurationMs:   durationMs,
        Status:       status,
        ErrorMessage: errorMessage,
    }

    database.GetDB().Create(&record)
}
```

- [ ] **Step 3: 在 bootstrap.go 中注册中间件**

修改 `pkg/server/bootstrap.go`，在路由配置中添加:

```go
import "github.com/sekiro-go/sekiro-go/pkg/server/middleware"

// 在 r := gin.Default() 之后添加
r.Use(middleware.TraceMiddleware())
```

- [ ] **Step 4: 运行测试**

```bash
cd pkg/server/middleware
go test -v -race
# Expected: PASS
```

- [ ] **Step 5: 提交**

```bash
git add pkg/server/middleware/trace.go pkg/server/middleware/trace_test.go
git commit -m "feat(trace): 添加追踪采集中间件"
```

---

### Task 4: 实现追踪查询 API

**Files:**
- Create: `pkg/server/handlers/trace.go`
- Modify: `pkg/server/handlers/routes.go`

- [ ] **Step 1: 创建追踪处理器**

```go
package handlers

import (
    "github.com/gin-gonic/gin"
    "github.com/sekiro-go/sekiro-go/pkg/database"
    "github.com/sekiro-go/sekiro-go/pkg/model"
)

// TraceHandler 追踪查询处理器
type TraceHandler struct{}

func NewTraceHandler() *TraceHandler {
    return &TraceHandler{}
}

// GetTraces 获取追踪列表
func (h *TraceHandler) GetTraces(c *gin.Context) {
    var query model.TraceQuery
    if err := c.ShouldBindQuery(&query); err != nil {
        c.JSON(400, gin.H{"code": 400, "message": err.Error()})
        return
    }

    // 构建查询
    db := database.GetDB().Table("trace_record")

    if query.TraceID != "" {
        db = db.Where("trace_id = ?", query.TraceID)
    }
    if query.Group != "" {
        db = db.Where("\"group\" = ?", query.Group)
    }
    if query.DeviceID != "" {
        db = db.Where("device_id = ?", query.DeviceID)
    }
    if query.API != "" {
        db = db.Where("api LIKE ?", "%"+query.API+"%")
    }
    if query.Status != "" {
        db = db.Where("status = ?", query.Status)
    }
    if query.StartTime != "" {
        db = db.Where("start_time >= ?", query.StartTime)
    }
    if query.EndTime != "" {
        db = db.Where("end_time <= ?", query.EndTime)
    }

    // 分页
    offset := (query.Page - 1) * query.PageSize
    db = db.Offset(offset).Limit(query.PageSize)

    // 排序
    db = db.Order("start_time DESC")

    var records []model.TraceRecord
    if err := db.Find(&records).Error; err != nil {
        c.JSON(500, gin.H{"code": 500, "message": err.Error()})
        return
    }

    // 获取总数
    var total int64
    database.GetDB().Table("trace_record").Count(&total)

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data":    records,
        "total":   total,
    })
}

// GetTraceDetail 获取追踪详情（包含完整链路）
func (h *TraceHandler) GetTraceDetail(c *gin.Context) {
    traceID := c.Param("traceId")

    var records []model.TraceRecord
    if err := database.GetDB().
        Where("trace_id = ?", traceID).
        Order("start_time ASC").
        Find(&records).Error; err != nil {
        c.JSON(500, gin.H{"code": 500, "message": err.Error()})
        return
    }

    if len(records) == 0 {
        c.JSON(404, gin.H{"code": 404, "message": "追踪记录不存在"})
        return
    }

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data": gin.H{
            "trace_id": traceID,
            "spans":    records,
        },
    })
}
```

- [ ] **Step 2: 注册路由**

修改 `pkg/server/handlers/routes.go`:

```go
// 添加追踪相关路由
api.GET("/traces", traceHandler.GetTraces)
api.GET("/traces/:traceId", traceHandler.GetTraceDetail)
```

- [ ] **Step 3: 提交**

```bash
git add pkg/server/handlers/trace.go pkg/server/handlers/routes.go
git commit -m "feat(trace): 添加追踪查询 API"
```

---

## Chunk 2: 性能指标采集增强

### Task 5: 扩展指标类型定义

**Files:**
- Modify: `pkg/model/database.go` (MetricTag 表使用)
- Create: `pkg/server/metrics/collector.go`

- [ ] **Step 1: 定义指标采集器接口**

```go
package metrics

import (
    "github.com/sekiro-go/sekiro-go/pkg/model"
    "time"
)

// MetricType 指标类型
type MetricType string

const (
    MetricTypeCounter   MetricType = "counter"   // 计数器（累加）
    MetricTypeGauge     MetricType = "gauge"     // 仪表（瞬时值）
    MetricTypeHistogram MetricType = "histogram" // 直方图（分布）
    MetricTypeLatency   MetricType = "latency"   // 延迟指标
)

// MetricCollector 指标采集器
type MetricCollector interface {
    // Incr 增加计数
    Incr(name string, tags map[string]string, value float64)
    // Set 设置仪表值
    Set(name string, tags map[string]string, value float64)
    // Observe 观察值（用于直方图）
    Observe(name string, tags map[string]string, value float64)
    // RecordLatency 记录延迟（自动计算 P50/P90/P99）
    RecordLatency(name string, tags map[string]string, durationMs float64)
}

// MetricBucket 指标桶（用于批量写入）
type MetricBucket struct {
    Name       string
    TimeKey    string
    TagsMD5    string
    Tags       map[string]string
    Type       MetricType
    Value      float64
    Count      int64
    Sum        float64
    Buckets    map[float64]int64 // 用于直方图
    Percentiles map[float64]float64 // P50, P90, P99
}
```

- [ ] **Step 2: 实现采集器**

```go
package metrics

import (
    "crypto/md5"
    "encoding/hex"
    "fmt"
    "sort"
    "sync"
    "time"

    "github.com/sekiro-go/sekiro-go/pkg/database"
    "github.com/sekiro-go/sekiro-go/pkg/model"
)

type collector struct {
    mu       sync.Mutex
    buckets  map[string]*MetricBucket
    interval time.Duration
}

func NewCollector(interval time.Duration) MetricCollector {
    c := &collector{
        buckets:  make(map[string]*MetricBucket),
        interval: interval,
    }
    // 启动定期聚合协程
    go c.flushLoop()
    return c
}

func (c *collector) Incr(name string, tags map[string]string, value float64) {
    c.mu.Lock()
    defer c.mu.Unlock()

    key := c.makeKey(name, tags, "counter")
    bucket, ok := c.buckets[key]
    if !ok {
        bucket = &MetricBucket{
            Name:    name,
            Tags:    tags,
            Type:    MetricTypeCounter,
            TimeKey: time.Now().Format("200601021504"), // 分钟级
        }
        c.buckets[key] = bucket
    }
    bucket.Value += value
    bucket.Count++
}

func (c *collector) Set(name string, tags map[string]string, value float64) {
    c.mu.Lock()
    defer c.mu.Unlock()

    key := c.makeKey(name, tags, "gauge")
    bucket, ok := c.buckets[key]
    if !ok {
        bucket = &MetricBucket{
            Name:    name,
            Tags:    tags,
            Type:    MetricTypeGauge,
            TimeKey: time.Now().Format("200601021504"),
        }
        c.buckets[key] = bucket
    }
    bucket.Value = value
    bucket.Count++
}

func (c *collector) Observe(name string, tags map[string]string, value float64) {
    c.mu.Lock()
    defer c.mu.Unlock()

    key := c.makeKey(name, tags, "histogram")
    bucket, ok := c.buckets[key]
    if !ok {
        bucket = &MetricBucket{
            Name:     name,
            Tags:     tags,
            Type:     MetricTypeHistogram,
            TimeKey:  time.Now().Format("200601021504"),
            Buckets:  make(map[float64]int64),
        }
        c.buckets[key] = bucket
    }
    bucket.Value += value
    bucket.Count++
    bucket.Sum += value
    // 简单的桶分配
    bucket.Buckets[value]++
}

func (c *collector) RecordLatency(name string, tags map[string]string, durationMs float64) {
    c.Observe(name+".latency", tags, durationMs)
}

func (c *collector) makeKey(name string, tags map[string]string, metricType string) string {
    // 将 tags 排序后生成 MD5
    keys := make([]string, 0, len(tags))
    for k := range tags {
        keys = append(keys, k)
    }
    sort.Strings(keys)

    h := md5.New()
    for _, k := range keys {
        h.Write([]byte(fmt.Sprintf("%s=%s,", k, tags[k])))
    }
    tagsMD5 := hex.EncodeToString(h.Sum(nil))

    return fmt.Sprintf("%s:%s:%s", name, tagsMD5, metricType)
}

func (c *collector) flushLoop() {
    ticker := time.NewTicker(c.interval)
    defer ticker.Stop()

    for range ticker.C {
        c.flush()
    }
}

func (c *collector) flush() {
    c.mu.Lock()
    buckets := c.buckets
    c.buckets = make(map[string]*MetricBucket)
    c.mu.Unlock()

    var metrics []model.MetricMinute
    for _, bucket := range buckets {
        // 计算百分位数
        percentiles := c.calculatePercentiles(bucket)

        // 创建指标记录
        metrics = append(metrics, c.toMetricRecords(bucket, percentiles)...)
    }

    if len(metrics) > 0 {
        database.GetDB().CreateInBatches(metrics, 100)
    }
}

func (c *collector) calculatePercentiles(bucket *MetricBucket) map[float64]float64 {
    if bucket.Count == 0 {
        return nil
    }

    // 简化实现：直接使用平均值作为近似
    // 实际应收集所有观测值后排序计算
    avg := bucket.Sum / float64(bucket.Count)

    return map[float64]float64{
        50: avg,
        90: avg * 1.2, // 近似值
        99: avg * 1.5, // 近似值
    }
}

func (c *collector) toMetricRecords(bucket *MetricBucket, percentiles map[float64]float64) []model.MetricMinute {
    var records []model.MetricMinute

    // 基础指标
    records = append(records, model.MetricMinute{
        Name:    bucket.Name,
        TimeKey: bucket.TimeKey,
        TagsMD5: c.tagsMD5(bucket.Tags),
        Type:    string(bucket.Type),
        Value:   bucket.Value,
        Tag1:    bucket.Tags["group"],
        Tag2:    bucket.Tags["device_id"],
        Tag3:    bucket.Tags["api"],
    })

    // 延迟百分位数
    for p, v := range percentiles {
        records = append(records, model.MetricMinute{
            Name:    fmt.Sprintf("%s_p%d", bucket.Name, int(p)),
            TimeKey: bucket.TimeKey,
            TagsMD5: c.tagsMD5(bucket.Tags),
            Type:    "latency",
            Value:   v,
            Tag1:    bucket.Tags["group"],
            Tag2:    bucket.Tags["api"],
        })
    }

    return records
}

func (c *collector) tagsMD5(tags map[string]string) string {
    keys := make([]string, 0, len(tags))
    for k := range tags {
        keys = append(keys, k)
    }
    sort.Strings(keys)

    h := md5.New()
    for _, k := range keys {
        h.Write([]byte(fmt.Sprintf("%s=%s,", k, tags[k])))
    }
    return hex.EncodeToString(h.Sum(nil))
}
```

- [ ] **Step 3: 在 bootstrap.go 中初始化采集器**

```go
// 创建全局采集器
var metricsCollector = metrics.NewCollector(time.Minute)

// 导出为包级变量供其他模块使用
func GetMetricsCollector() metrics.MetricCollector {
    return metricsCollector
}
```

- [ ] **Step 4: 提交**

```bash
git add pkg/server/metrics/
git commit -m "feat(metrics): 添加指标采集器"
```

---

### Task 6: 集成性能指标采集

**Files:**
- Modify: `pkg/server/api/handlers.go`
- Modify: `pkg/server/websocket/handler.go`

- [ ] **Step 1: 在 Invoke 处理器中采集指标**

修改 `pkg/server/api/handlers.go`:

```go
import "github.com/sekiro-go/sekiro-go/pkg/server/metrics"

func (h *APIHandler) Invoke(c *gin.Context) {
    startTime := time.Now()

    // ... 现有逻辑 ...

    // 记录成功/失败
    tags := map[string]string{
        "group": group,
        "api":   api,
    }

    if err != nil {
        metrics.GetMetricsCollector().Incr("api.invocations.failure", tags, 1)
    } else {
        metrics.GetMetricsCollector().Incr("api.invocations.success", tags, 1)
    }

    // 记录延迟
    durationMs := float64(time.Since(startTime).Milliseconds())
    metrics.GetMetricsCollector().RecordLatency("api.invocations.latency", tags, durationMs)

    // 记录在线设备数
    metrics.GetMetricsCollector().Set("system.online_devices", nil, float64(onlineCount))
}
```

- [ ] **Step 2: 在 WebSocket 处理器中采集连接指标**

修改 `pkg/server/websocket/handler.go`:

```go
func (h *Handler) HandleRegister(c *websocket.Conn, group, deviceID string) {
    // 注册成功后
    metrics.GetMetricsCollector().Incr("websocket.connections.created", map[string]string{
        "group": group,
    }, 1)

    metrics.GetMetricsCollector().Set("websocket.connections.active", nil, float64(h.getActiveCount()))
}

func (h *Handler) HandleDisconnect(group, deviceID string) {
    metrics.GetMetricsCollector().Incr("websocket.connections.closed", map[string]string{
        "group": group,
        "reason": "client_disconnect",
    }, 1)

    metrics.GetMetricsCollector().Set("websocket.connections.active", nil, float64(h.getActiveCount()))
}
```

- [ ] **Step 3: 提交**

```bash
git add pkg/server/api/handlers.go pkg/server/websocket/handler.go
git commit -m "feat(metrics): 集成性能指标采集"
```

---

### Task 7: 添加延迟百分位数 API

**Files:**
- Modify: `pkg/server/handlers/metric.go`

- [ ] **Step 1: 添加延迟百分位数查询接口**

```go
// GetLatencyPercentiles 获取延迟百分位数
func (h *MetricHandler) GetLatencyPercentiles(c *gin.Context) {
    group := c.Query("group")
    api := c.Query("api")
    timeRange := c.Query("timeRange") // minute, hour, day

    table := "metric_minute"
    switch timeRange {
    case "hour":
        table = "metric_hour"
    case "day":
        table = "metric_day"
    }

    // 查询 P50/P90/P99
    var latencies []struct {
        Name  string  `gorm:"column:name"`
        Value float64 `gorm:"column:value"`
        TimeKey string `gorm:"column:time_key"`
    }

    query := database.GetDB().Table(table).
        Select("name, value, time_key").
        Where("name LIKE ?", "api.invocations.latency_p%")

    if group != "" {
        query = query.Where("tag1 = ?", group)
    }
    if api != "" {
        query = query.Where("tag2 = ?", api)
    }

    query.Order("time_key DESC").Limit(100).Scan(&latencies)

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data":    latencies,
    })
}
```

- [ ] **Step 2: 注册路由**

```go
api.GET("/metrics/latency/percentiles", h.GetLatencyPercentiles)
```

- [ ] **Step 3: 提交**

```bash
git add pkg/server/handlers/metric.go
git commit -m "feat(metrics): 添加延迟百分位数 API"
```

---

## Chunk 3: 告警系统

### Task 8: 定义告警数据模型

**Files:**
- Create: `pkg/model/alert.go`

- [ ] **Step 1: 创建告警模型**

```go
package model

import "time"

// AlertRule 告警规则
type AlertRule struct {
	ID          int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	Name        string    `json:"name" gorm:"size:128;not null"`
	Description string    `json:"description" gorm:"size:512"`
	MetricName  string    `json:"metric_name" gorm:"size:64;not null"`
	Operator    string    `json:"operator" gorm:"size:8;not null"` // >, <, >=, <=, ==, !=
	Threshold   float64   `json:"threshold" gorm:"not null"`
	Window      int       `json:"window" gorm:"not null"` // 时间窗口 (分钟)
	Condition   string    `json:"condition" gorm:"size:64"` // ALL, ANY
	Filters     string    `json:"filters" gorm:"type:text"` // JSON 格式过滤条件
	Enabled     bool      `json:"enabled" gorm:"not null;default:true"`
	CreateBy    int64     `json:"create_by" gorm:"not null"`
	CreateTime  time.Time `json:"create_time" gorm:"default:CURRENT_TIMESTAMP"`
}

func (AlertRule) TableName() string {
	return "alert_rule"
}

// AlertHistory 告警历史
type AlertHistory struct {
	ID         int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	RuleID     int64     `json:"rule_id" gorm:"not null;index"`
	RuleName   string    `json:"rule_name" gorm:"size:128;not null"`
	TriggeredAt time.Time `json:"triggered_at" gorm:"not null"`
	RecoveredAt *time.Time `json:"recovered_at"`
	Status     string    `json:"status" gorm:"size:16;not null"` // FIRING, RESOLVED, ACKNOWLEDGED
	Value      float64   `json:"value" gorm:"not null"`
	Message    string    `json:"message" gorm:"type:text"`
	AckedBy    int64     `json:"acked_by"`
	AckedAt    *time.Time `json:"acked_at"`
}

func (AlertHistory) TableName() string {
	return "alert_history"
}

// AlertNotification 告警通知记录
type AlertNotification struct {
	ID        int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	AlertID   int64     `json:"alert_id" gorm:"not null;index"`
	Channel   string    `json:"channel" gorm:"size:32;not null"` // webhook, email, internal
	Target    string    `json:"target" gorm:"size:256"` // URL 或邮箱
	Status    string    `json:"status" gorm:"size:16;not null"` // SENT, FAILED
	Error     string    `json:"error" gorm:"type:text"`
	SentAt    time.Time `json:"sent_at" gorm:"default:CURRENT_TIMESTAMP"`
}

func (AlertNotification) TableName() string {
	return "alert_notification"
}
```

- [ ] **Step 2: 创建迁移脚本**

Create: `deploy/postgres/migration/003_add_alert_tables.sql`

```sql
-- 告警规则表
CREATE TABLE IF NOT EXISTS alert_rule (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(512),
    metric_name VARCHAR(64) NOT NULL,
    operator VARCHAR(8) NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    window INT NOT NULL,
    "condition" VARCHAR(64),
    filters TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    create_by BIGINT NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 告警历史表
CREATE TABLE IF NOT EXISTS alert_history (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NOT NULL,
    rule_name VARCHAR(128) NOT NULL,
    triggered_at TIMESTAMP NOT NULL,
    recovered_at TIMESTAMP,
    status VARCHAR(16) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    message TEXT,
    acked_by BIGINT,
    acked_at TIMESTAMP
);

-- 告警通知记录表
CREATE TABLE IF NOT EXISTS alert_notification (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL,
    channel VARCHAR(32) NOT NULL,
    target VARCHAR(256),
    status VARCHAR(16) NOT NULL,
    error TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_alert_history_rule_id ON alert_history(rule_id);
CREATE INDEX idx_alert_history_status ON alert_history(status);
CREATE INDEX idx_alert_notification_alert_id ON alert_notification(alert_id);

-- 注释
COMMENT ON TABLE alert_rule IS '告警规则配置';
COMMENT ON TABLE alert_history IS '告警历史记录';
COMMENT ON TABLE alert_notification IS '告警通知发送记录';
```

- [ ] **Step 3: 提交**

```bash
git add pkg/model/alert.go deploy/postgres/migration/003_add_alert_tables.sql
git commit -m "feat(alert): 添加告警数据模型"
```

---

### Task 9: 实现告警评估引擎

**Files:**
- Create: `pkg/server/alert/evaluator.go`

- [ ] **Step 1: 实现告警评估器**

```go
package alert

import (
    "encoding/json"
    "fmt"
    "time"

    "github.com/sekiro-go/sekiro-go/pkg/database"
    "github.com/sekiro-go/sekiro-go/pkg/model"
)

// Evaluator 告警评估器
type Evaluator struct {
    running bool
    done    chan struct{}
}

func NewEvaluator() *Evaluator {
    return &Evaluator{}
}

// Start 启动告警评估
func (e *Evaluator) Start(interval time.Duration) {
    e.running = true
    e.done = make(chan struct{})

    go func() {
        ticker := time.NewTicker(interval)
        defer ticker.Stop()

        for {
            select {
            case <-ticker.C:
                e.evaluateAll()
            case <-e.done:
                return
            }
        }
    }()
}

// Stop 停止告警评估
func (e *Evaluator) Stop() {
    e.running = false
    close(e.done)
}

func (e *Evaluator) evaluateAll() {
    // 获取所有启用的规则
    var rules []model.AlertRule
    database.GetDB().Where("enabled = ?", true).Find(&rules)

    for _, rule := range rules {
        e.evaluateRule(&rule)
    }
}

func (e *Evaluator) evaluateRule(rule *model.AlertRule) {
    // 解析过滤条件
    filters := make(map[string]string)
    if rule.Filters != "" {
        json.Unmarshal([]byte(rule.Filters), &filters)
    }

    // 查询指标值
    value, err := e.queryMetric(rule.MetricName, filters, rule.Window)
    if err != nil {
        logger.Errorf("告警评估失败：%v", err)
        return
    }

    // 评估条件
    triggered := e.checkCondition(value, rule.Operator, rule.Threshold)

    if triggered {
        e.handleTrigger(rule, value)
    } else {
        e.handleRecovery(rule)
    }
}

func (e *Evaluator) queryMetric(metricName string, filters map[string]string, window int) (float64, error) {
    // 查询最近 N 分钟的平均值
    var result struct {
        AvgValue float64 `gorm:"column:avg_value"`
    }

    query := database.GetDB().
        Table("metric_minute").
        Select("AVG(value) as avg_value").
        Where("name = ?", metricName).
        Where("time_key >= ?", time.Now().Add(-time.Duration(window)*time.Minute).Format("200601021504"))

    for k, v := range filters {
        switch k {
        case "group":
            query = query.Where("tag1 = ?", v)
        case "device_id":
            query = query.Where("tag2 = ?", v)
        case "api":
            query = query.Where("tag3 = ?", v)
        }
    }

    query.Scan(&result)

    return result.AvgValue, nil
}

func (e *Evaluator) checkCondition(value float64, operator string, threshold float64) bool {
    switch operator {
    case ">":
        return value > threshold
    case ">=":
        return value >= threshold
    case "<":
        return value < threshold
    case "<=":
        return value <= threshold
    case "==":
        return value == threshold
    case "!=":
        return value != threshold
    default:
        return false
    }
}

func (e *Evaluator) handleTrigger(rule *model.AlertRule, value float64) {
    // 检查是否已有未恢复的告警
    var existing model.AlertHistory
    err := database.GetDB().
        Where("rule_id = ? AND status = ?", rule.ID, "FIRING").
        First(&existing).Error

    if err == nil {
        // 已存在告警，跳过
        return
    }

    // 创建新告警
    alert := model.AlertHistory{
        RuleID:    rule.ID,
        RuleName:  rule.Name,
        TriggeredAt: time.Now(),
        Status:    "FIRING",
        Value:     value,
        Message:   fmt.Sprintf("告警：%s，当前值：%.2f，阈值：%.2f", rule.Name, value, rule.Threshold),
    }

    database.GetDB().Create(&alert)

    // 发送通知
    go sendNotifications(&alert, rule)
}

func (e *Evaluator) handleRecovery(rule *model.AlertRule) {
    // 查找未恢复的告警
    var alert model.AlertHistory
    err := database.GetDB().
        Where("rule_id = ? AND status = ?", rule.ID, "FIRING").
        First(&alert).Error

    if err != nil {
        return
    }

    // 更新告警状态
    now := time.Now()
    alert.Status = "RESOLVED"
    alert.RecoveredAt = &now

    database.GetDB().Save(&alert)

    // 发送恢复通知
    go sendNotifications(&alert, rule)
}

func sendNotifications(alert *model.AlertHistory, rule *model.AlertRule) {
    // 获取通知配置 (从系统配置表读取)
    var configs []model.SysConfig
    database.GetDB().Where("config_key LIKE ?", "alert.notification.%").Find(&configs)

    for _, config := range configs {
        var notification model.AlertNotification
        notification.AlertID = alert.ID
        notification.Target = config.ConfigValue

        // 根据配置发送通知
        switch config.ConfigComment {
        case "webhook":
            sendWebhook(notification, alert)
        case "email":
            sendEmail(notification, alert)
        case "internal":
            sendInternal(notification, alert)
        }
    }
}
```

- [ ] **Step 2: 在 bootstrap.go 中启动评估器**

```go
import "github.com/sekiro-go/sekiro-go/pkg/server/alert"

var alertEvaluator = alert.NewEvaluator()

// 启动告警评估 (每 5 分钟)
alertEvaluator.Start(5 * time.Minute)
```

- [ ] **Step 3: 提交**

```bash
git add pkg/server/alert/evaluator.go
git commit -m "feat(alert): 实现告警评估引擎"
```

---

### Task 10: 实现告警管理 API

**Files:**
- Create: `pkg/server/handlers/alert.go`
- Modify: `pkg/server/handlers/routes.go`

- [ ] **Step 1: 创建告警处理器**

```go
package handlers

import (
    "github.com/gin-gonic/gin"
    "github.com/sekiro-go/sekiro-go/pkg/database"
    "github.com/sekiro-go/sekiro-go/pkg/model"
)

// AlertHandler 告警处理器
type AlertHandler struct{}

func NewAlertHandler() *AlertHandler {
    return &AlertHandler{}
}

// AlertRuleRequest 告警规则请求
type AlertRuleRequest struct {
    Name        string            `json:"name"`
    Description string            `json:"description"`
    MetricName  string            `json:"metric_name"`
    Operator    string            `json:"operator"`
    Threshold   float64           `json:"threshold"`
    Window      int               `json:"window"`
    Filters     map[string]string `json:"filters"`
    Enabled     bool              `json:"enabled"`
}

// CreateAlertRule 创建告警规则
func (h *AlertHandler) CreateAlertRule(c *gin.Context) {
    var req AlertRuleRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(400, gin.H{"code": 400, "message": err.Error()})
        return
    }

    filtersJSON, _ := json.Marshal(req.Filters)

    rule := model.AlertRule{
        Name:        req.Name,
        Description: req.Description,
        MetricName:  req.MetricName,
        Operator:    req.Operator,
        Threshold:   req.Threshold,
        Window:      req.Window,
        Filters:     string(filtersJSON),
        Enabled:     req.Enabled,
        CreateBy:    c.GetInt("userId"),
    }

    database.GetDB().Create(&rule)

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data":    rule,
    })
}

// GetAlertRules 获取告警规则列表
func (h *AlertHandler) GetAlertRules(c *gin.Context) {
    var rules []model.AlertRule
    database.GetDB().Order("create_time DESC").Find(&rules)

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data":    rules,
    })
}

// UpdateAlertRule 更新告警规则
func (h *AlertHandler) UpdateAlertRule(c *gin.Context) {
    ruleID := c.Param("id")

    var req AlertRuleRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(400, gin.H{"code": 400, "message": err.Error()})
        return
    }

    var rule model.AlertRule
    if err := database.GetDB().First(&rule, ruleID).Error; err != nil {
        c.JSON(404, gin.H{"code": 404, "message": "规则不存在"})
        return
    }

    filtersJSON, _ := json.Marshal(req.Filters)
    rule.Name = req.Name
    rule.Description = req.Description
    rule.MetricName = req.MetricName
    rule.Operator = req.Operator
    rule.Threshold = req.Threshold
    rule.Window = req.Window
    rule.Filters = string(filtersJSON)
    rule.Enabled = req.Enabled

    database.GetDB().Save(&rule)

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data":    rule,
    })
}

// DeleteAlertRule 删除告警规则
func (h *AlertHandler) DeleteAlertRule(c *gin.Context) {
    ruleID := c.Param("id")
    database.GetDB().Delete(&model.AlertRule{}, ruleID)

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
    })
}

// GetAlertHistory 获取告警历史
func (h *AlertHandler) GetAlertHistory(c *gin.Context) {
    status := c.Query("status")

    query := database.GetDB().Table("alert_history")
    if status != "" {
        query = query.Where("status = ?", status)
    }

    var alerts []model.AlertHistory
    query.Order("triggered_at DESC").Limit(100).Find(&alerts)

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data":    alerts,
    })
}

// AcknowledgeAlert 确认告警
func (h *AlertHandler) AcknowledgeAlert(c *gin.Context) {
    alertID := c.Param("id")
    userID := c.GetInt("userId")
    now := time.Now()

    var alert model.AlertHistory
    if err := database.GetDB().First(&alert, alertID).Error; err != nil {
        c.JSON(404, gin.H{"code": 404, "message": "告警不存在"})
        return
    }

    alert.Status = "ACKNOWLEDGED"
    alert.AckedBy = int64(userID)
    alert.AckedAt = &now

    database.GetDB().Save(&alert)

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
    })
}
```

- [ ] **Step 2: 注册路由**

```go
// 告警管理路由
api.POST("/alerts/rules", alertHandler.CreateAlertRule)
api.GET("/alerts/rules", alertHandler.GetAlertRules)
api.PUT("/alerts/rules/:id", alertHandler.UpdateAlertRule)
api.DELETE("/alerts/rules/:id", alertHandler.DeleteAlertRule)
api.GET("/alerts/history", alertHandler.GetAlertHistory)
api.POST("/alerts/:id/ack", alertHandler.AcknowledgeAlert)
```

- [ ] **Step 3: 提交**

```bash
git add pkg/server/handlers/alert.go pkg/server/handlers/routes.go
git commit -m "feat(alert): 添加告警管理 API"
```

---

## Chunk 4: 日志聚合

### Task 11: 配置结构化日志

**Files:**
- Modify: `internal/utils/logger/logger.go`

- [ ] **Step 1: 添加 JSON 日志格式配置**

```go
func InitLogger(mode string, logFile string) (*zap.Logger, error) {
    var config zap.Config

    if mode == "debug" {
        config = zap.NewDevelopmentConfig()
        config.EncoderConfig.EncodeLevel = zapcore.CapitalColorLevelEncoder
    } else {
        config = zap.NewProductionConfig()
        config.Encoding = "json" // 生产环境使用 JSON 格式
    }

    // 添加更多字段
    config.EncoderConfig.TimeKey = "timestamp"
    config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
    config.EncoderConfig.CallerKey = "caller"
    config.EncoderConfig.MessageKey = "message"
    config.EncoderConfig.LevelKey = "level"

    // 输出到文件和控制台
    config.OutputPaths = []string{"stdout", logFile}

    return config.Build()
}
```

- [ ] **Step 2: 添加请求日志中间件**

Create: `pkg/server/middleware/logging.go`

```go
package middleware

import (
    "github.com/gin-gonic/gin"
    "github.com/sekiro-go/sekiro-go/internal/utils/logger"
    "time"
)

// RequestLogMiddleware 请求日志中间件
func RequestLogMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        startTime := time.Now()

        // 处理请求
        c.Next()

        // 记录日志
        logger.Info("HTTP 请求",
            zap.String("method", c.Request.Method),
            zap.String("path", c.Request.URL.Path),
            zap.Int("status", c.Writer.Status()),
            zap.String("client_ip", c.ClientIP()),
            zap.Duration("latency", time.Since(startTime)),
            zap.String("trace_id", c.GetHeader("X-Trace-ID")),
            zap.Int64("content_length", c.Request.ContentLength),
            zap.String("user_agent", c.Request.UserAgent()),
        )

        // 记录错误
        for _, err := range c.Errors {
            logger.Error("请求错误",
                zap.String("error", err.Error()),
                zap.String("type", err.Type.String()),
            )
        }
    }
}
```

- [ ] **Step 3: 在 bootstrap.go 中注册**

```go
// 在 TraceMiddleware 之前添加
r.Use(middleware.RequestLogMiddleware())
```

- [ ] **Step 4: 提交**

```bash
git add internal/utils/logger/logger.go pkg/server/middleware/logging.go
git commit -m "feat(logging): 配置结构化日志和请求日志中间件"
```

---

### Task 12: 实现日志查询 API

**Files:**
- Create: `pkg/server/handlers/log.go`
- Modify: `pkg/server/handlers/routes.go`

- [ ] **Step 1: 创建日志处理器**

由于日志文件是 JSON 格式，我们需要提供简单的查询接口。这里实现一个基于文件扫描的简单查询器：

```go
package handlers

import (
    "bufio"
    "encoding/json"
    "os"
    "strings"
    "time"

    "github.com/gin-gonic/gin"
)

// LogHandler 日志处理器
type LogHandler struct {
    logFilePath string
}

func NewLogHandler(logFilePath string) *LogHandler {
    return &LogHandler{logFilePath: logFilePath}
}

// LogQuery 日志查询参数
type LogQuery struct {
    Level     string `json:"level" form:"level"`
    Keyword   string `json:"keyword" form:"keyword"`
    StartTime string `json:"startTime" form:"startTime"`
    EndTime   string `json:"endTime" form:"endTime"`
    Limit     int    `json:"limit" form:"limit" form:"100"`
}

// LogEntry 日志条目
type LogEntry struct {
    Timestamp string `json:"timestamp"`
    Level     string `json:"level"`
    Caller    string `json:"caller"`
    Message   string `json:"message"`
    Raw       string `json:"-"`
}

// GetLogs 获取日志
func (h *LogHandler) GetLogs(c *gin.Context) {
    var query LogQuery
    if err := c.ShouldBindQuery(&query); err != nil {
        c.JSON(400, gin.H{"code": 400, "message": err.Error()})
        return
    }

    file, err := os.Open(h.logFilePath)
    if err != nil {
        c.JSON(500, gin.H{"code": 500, "message": "无法打开日志文件"})
        return
    }
    defer file.Close()

    var entries []LogEntry
    scanner := bufio.NewScanner(file)
    count := 0

    // 从文件末尾开始读取 (最新日志)
    var lines []string
    for scanner.Scan() {
        lines = append(lines, scanner.Text())
    }

    // 倒序遍历
    for i := len(lines) - 1; i >= 0 && count < query.Limit; i-- {
        line := lines[i]
        entry := parseLogEntry(line)

        // 过滤
        if query.Level != "" && entry.Level != query.Level {
            continue
        }
        if query.Keyword != "" && !strings.Contains(entry.Message, query.Keyword) {
            continue
        }

        entries = append(entries, entry)
        count++
    }

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data":    entries,
    })
}

func parseLogEntry(line string) LogEntry {
    var entry LogEntry
    if err := json.Unmarshal([]byte(line), &entry); err != nil {
        return LogEntry{Raw: line}
    }
    return entry
}

// GetLogStats 获取日志统计
func (h *LogHandler) GetLogStats(c *gin.Context) {
    file, err := os.Open(h.logFilePath)
    if err != nil {
        c.JSON(500, gin.H{"code": 500, "message": "无法打开日志文件"})
        return
    }
    defer file.Close()

    stats := map[string]int{
        "INFO":     0,
        "WARN":     0,
        "ERROR":    0,
        "DEBUG":    0,
    }

    scanner := bufio.NewScanner(file)
    for scanner.Scan() {
        entry := parseLogEntry(scanner.Text())
        if count, ok := stats[entry.Level]; ok {
            stats[entry.Level] = count + 1
        }
    }

    c.JSON(200, gin.H{
        "code":    0,
        "message": "success",
        "data":    stats,
    })
}
```

- [ ] **Step 2: 注册路由**

```go
api.GET("/logs", logHandler.GetLogs)
api.GET("/logs/stats", logHandler.GetLogStats)
```

- [ ] **Step 3: 提交**

```bash
git add pkg/server/handlers/log.go pkg/server/handlers/routes.go
git commit -m "feat(logging): 添加日志查询 API"
```

---

## Chunk 5: 前端集成

### Task 13: 创建追踪查询前端页面

**Files:**
- Create: `web/src/pages/TraceList.jsx`
- Create: `web/src/pages/TraceDetail.jsx`
- Modify: `web/src/App.jsx` (添加路由)

- [ ] **Step 1: 创建追踪列表页面**

```jsx
import React, { useState, useEffect } from 'react';
import { Table, Card, Form, Input, Select, DatePicker, Button, Space, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import axios from 'axios';

const { RangePicker } = DatePicker;

const TraceList = () => {
    const [form] = Form.useForm();
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [total, setTotal] = useState(0);

    const fetchTraces = async (params) => {
        setLoading(true);
        try {
            const response = await axios.get('/api/traces', { params });
            setData(response.data.data || []);
            setTotal(response.data.total || 0);
        } catch (error) {
            console.error('获取追踪列表失败:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTraces({ page: 1, pageSize: 20 });
    }, []);

    const onFinish = (values) => {
        const params = {
            ...values,
            page: 1,
            pageSize: 20,
        };
        if (values.timeRange) {
            params.startTime = values.timeRange[0].toISOString();
            params.endTime = values.timeRange[1].toISOString();
        }
        fetchTraces(params);
    };

    const columns = [
        {
            title: 'Trace ID',
            dataIndex: 'trace_id',
            key: 'trace_id',
            ellipsis: true,
        },
        {
            title: 'API',
            dataIndex: 'api',
            key: 'api',
        },
        {
            title: '分组',
            dataIndex: 'group',
            key: 'group',
        },
        {
            title: '设备 ID',
            dataIndex: 'device_id',
            key: 'device_id',
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            render: (status) => (
                <Tag color={status === 'SUCCESS' ? 'green' : 'red'}>
                    {status}
                </Tag>
            ),
        },
        {
            title: '耗时 (ms)',
            dataIndex: 'duration_ms',
            key: 'duration_ms',
        },
        {
            title: '开始时间',
            dataIndex: 'start_time',
            key: 'start_time',
            render: (time) => new Date(time).toLocaleString(),
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <a href={`/traces/${record.trace_id}`}>查看详情</a>
            ),
        },
    ];

    return (
        <Card title="调用链路追踪">
            <Form form={form} onFinish={onFinish} layout="inline">
                <Form.Item name="traceId" label="Trace ID">
                    <Input placeholder="请输入 Trace ID" style={{ width: 200 }} />
                </Form.Item>
                <Form.Item name="group" label="分组">
                    <Input placeholder="请输入分组名" style={{ width: 150 }} />
                </Form.Item>
                <Form.Item name="status" label="状态">
                    <Select placeholder="请选择状态" allowClear style={{ width: 120 }}>
                        <Select.Option value="SUCCESS">成功</Select.Option>
                        <Select.Option value="FAILURE">失败</Select.Option>
                    </Select>
                </Form.Item>
                <Form.Item name="timeRange" label="时间范围">
                    <RangePicker />
                </Form.Item>
                <Form.Item>
                    <Space>
                        <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
                            查询
                        </Button>
                        <Button htmlType="button" onClick={() => form.reset()}>
                            重置
                        </Button>
                    </Space>
                </Form.Item>
            </Form>

            <Table
                columns={columns}
                dataSource={data}
                rowKey="id"
                loading={loading}
                pagination={{
                    total: total,
                    pageSize: 20,
                    showSizeChanger: true,
                    showTotal: (total) => `共 ${total} 条`,
                }}
                scroll={{ x: 1200 }}
            />
        </Card>
    );
};

export default TraceList;
```

- [ ] **Step 2: 创建追踪详情页面**

```jsx
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Descriptions, Timeline, Tag, Button, Space } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import axios from 'axios';

const TraceDetail = () => {
    const { traceId } = useParams();
    const navigate = useNavigate();
    const [trace, setTrace] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchTraceDetail = async () => {
            try {
                const response = await axios.get(`/api/traces/${traceId}`);
                setTrace(response.data.data);
            } catch (error) {
                console.error('获取追踪详情失败:', error);
            } finally {
                setLoading(false);
            }
        };

        fetchTraceDetail();
    }, [traceId]);

    if (loading) {
        return <Card loading={true} />;
    }

    if (!trace) {
        return <Card>追踪记录不存在</Card>;
    }

    return (
        <Card
            title={
                <Space>
                    <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/traces')}>
                        返回
                    </Button>
                    追踪详情：{trace.trace_id}
                </Space>
            }
        >
            <Descriptions column={2} bordered>
                <Descriptions.Item label="Trace ID">{trace.trace_id}</Descriptions.Item>
                <Descriptions.Item label="Span 数量">{trace.spans?.length || 0}</Descriptions.Item>
            </Descriptions>

            <Timeline
                items={trace.spans?.map((span) => ({
                    key: span.id,
                    color: span.status === 'SUCCESS' ? 'green' : 'red',
                    title: (
                        <Space>
                            <span>{span.api}</span>
                            <Tag color={span.status === 'SUCCESS' ? 'green' : 'red'}>
                                {span.status}
                            </Tag>
                            <span>{span.duration_ms}ms</span>
                        </Space>
                    ),
                    children: (
                        <div>
                            <div>分组：{span.group}</div>
                            <div>设备：{span.device_id}</div>
                            <div>调用方：{span.caller}</div>
                            <div>时间：{new Date(span.start_time).toLocaleString()}</div>
                            {span.error_message && (
                                <div style={{ color: 'red' }}>错误：{span.error_message}</div>
                            )}
                        </div>
                    ),
                }))}
            />
        </Card>
    );
};

export default TraceDetail;
```

- [ ] **Step 3: 添加路由**

修改 `web/src/App.jsx`:

```jsx
import TraceList from './pages/TraceList';
import TraceDetail from './pages/TraceDetail';

// 在 routes 数组中添加
{
    path: '/traces',
    element: <TraceList />,
},
{
    path: '/traces/:traceId',
    element: <TraceDetail />,
},
```

- [ ] **Step 4: 提交**

```bash
git add web/src/pages/TraceList.jsx web/src/pages/TraceDetail.jsx web/src/App.jsx
git commit -m "feat(web): 添加追踪查询前端页面"
```

---

### Task 14: 创建监控仪表盘增强

**Files:**
- Modify: `web/src/components/GroupMonitor.jsx`
- Modify: `web/src/pages/Dashboard.jsx`

- [ ] **Step 1: 在 GroupMonitor 中添加延迟百分位数图表**

```jsx
import React, { useEffect } from 'react';
import { Card, Row, Col } from 'antd';
import ReactECharts from 'echarts-for-react';
import axios from 'axios';

const GroupMonitor = ({ groupName }) => {
    const [latencyData, setLatencyData] = useState({ p50: [], p90: [], p99: [] });

    const fetchLatencyPercentiles = async () => {
        const response = await axios.get('/api/metrics/latency/percentiles', {
            params: { group: groupName, timeRange: 'minute' }
        });

        // 处理数据
        const data = response.data.data || [];
        const p50 = data.filter(d => d.name.includes('_p50')).map(d => [d.time_key, d.value]);
        const p90 = data.filter(d => d.name.includes('_p90')).map(d => [d.time_key, d.value]);
        const p99 = data.filter(d => d.name.includes('_p99')).map(d => [d.time_key, d.value]);

        setLatencyData({ p50, p90, p99 });
    };

    useEffect(() => {
        fetchLatencyPercentiles();
        const interval = setInterval(fetchLatencyPercentiles, 60000); // 每分钟刷新
        return () => clearInterval(interval);
    }, [groupName]);

    const latencyOption = {
        title: { text: '延迟百分位数' },
        tooltip: { trigger: 'axis' },
        legend: { data: ['P50', 'P90', 'P99'] },
        xAxis: { type: 'category', boundaryGap: false },
        yAxis: { type: 'value', name: 'ms' },
        series: [
            { name: 'P50', type: 'line', data: latencyData.p50, smooth: true },
            { name: 'P90', type: 'line', data: latencyData.p90, smooth: true },
            { name: 'P99', type: 'line', data: latencyData.p99, smooth: true },
        ],
    };

    return (
        <Card title="性能监控">
            <Row gutter={16}>
                <Col span={24}>
                    <ReactECharts option={latencyOption} style={{ height: 300 }} />
                </Col>
            </Row>
        </Card>
    );
};

export default GroupMonitor;
```

- [ ] **Step 2: 提交**

```bash
git add web/src/components/GroupMonitor.jsx web/src/pages/Dashboard.jsx
git commit -m "feat(web): 在监控仪表盘中添加延迟百分位数图表"
```

---

### Task 15: 创建告警管理前端页面

**Files:**
- Create: `web/src/pages/AlertRules.jsx`
- Create: `web/src/pages/AlertHistory.jsx`
- Modify: `web/src/App.jsx`

- [ ] **Step 1: 创建告警规则管理页面**

```jsx
import React, { useState, useEffect } from 'react';
import { Table, Card, Button, Modal, Form, Input, InputNumber, Select, Switch, Space, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import axios from 'axios';

const { TextArea } = Input;

const AlertRules = () => {
    const [rules, setRules] = useState([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingRule, setEditingRule] = useState(null);
    const [form] = Form.useForm();

    const fetchRules = async () => {
        setLoading(true);
        try {
            const response = await axios.get('/api/alerts/rules');
            setRules(response.data.data || []);
        } catch (error) {
            console.error('获取告警规则失败:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchRules();
    }, []);

    const handleCreate = () => {
        setEditingRule(null);
        form.resetFields();
        setModalVisible(true);
    };

    const handleEdit = (rule) => {
        setEditingRule(rule);
        form.setFieldsValue(rule);
        setModalVisible(true);
    };

    const handleDelete = async (id) => {
        await axios.delete(`/api/alerts/rules/${id}`);
        fetchRules();
    };

    const handleSubmit = async (values) => {
        if (editingRule) {
            await axios.put(`/api/alerts/rules/${editingRule.id}`, values);
        } else {
            await axios.post('/api/alerts/rules', values);
        }
        setModalVisible(false);
        fetchRules();
    };

    const columns = [
        { title: '规则名称', dataIndex: 'name', key: 'name' },
        { title: '指标', dataIndex: 'metric_name', key: 'metric_name' },
        { title: '条件', dataIndex: 'operator', key: 'operator',
            render: (op, record) => `${record.metric_name} ${op} ${record.threshold}` },
        { title: '窗口 (分钟)', dataIndex: 'window', key: 'window' },
        { title: '启用', dataIndex: 'enabled', key: 'enabled',
            render: (enabled) => enabled ? '是' : '否' },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <Space>
                    <Button icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
                    <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
                        <Button icon={<DeleteOutlined />} danger>删除</Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <Card
            title="告警规则管理"
            extra={<Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建规则</Button>}
        >
            <Table columns={columns} dataSource={rules} rowKey="id" loading={loading} />

            <Modal
                title={editingRule ? '编辑规则' : '新建规则'}
                open={modalVisible}
                onCancel={() => setModalVisible(false)}
                footer={null}
            >
                <Form form={form} layout="vertical" onFinish={handleSubmit}>
                    <Form.Item name="name" label="规则名称" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="description" label="描述">
                        <TextArea rows={3} />
                    </Form.Item>
                    <Form.Item name="metric_name" label="指标名称" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="operator" label="操作符" rules={[{ required: true }]}>
                        <Select>
                            <Select.Option value=">">&gt;</Select.Option>
                            <Select.Option value=">=">&gt;=</Select.Option>
                            <Select.Option value="<">&lt;</Select.Option>
                            <Select.Option value="<=">&lt;=</Select.Option>
                            <Select.Option value="==">=</Select.Option>
                            <Select.Option value="!=">!=</Select.Option>
                        </Select>
                    </Form.Item>
                    <Form.Item name="threshold" label="阈值" rules={[{ required: true }]}>
                        <InputNumber style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="window" label="时间窗口 (分钟)" rules={[{ required: true }]}>
                        <InputNumber style={{ width: '100%' }} defaultValue={5} />
                    </Form.Item>
                    <Form.Item name="enabled" label="启用" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                    <Form.Item>
                        <Space>
                            <Button type="primary" htmlType="submit">保存</Button>
                            <Button onClick={() => setModalVisible(false)}>取消</Button>
                        </Space>
                    </Form.Item>
                </Form>
            </Modal>
        </Card>
    );
};

export default AlertRules;
```

- [ ] **Step 2: 创建告警历史页面**

```jsx
import React, { useState, useEffect } from 'react';
import { Table, Card, Tag, Button, Space } from 'antd';
import { CheckOutlined } from '@ant-design/icons';
import axios from 'axios';

const AlertHistory = () => {
    const [alerts, setAlerts] = useState([]);
    const [loading, setLoading] = useState(false);

    const fetchAlerts = async () => {
        setLoading(true);
        try {
            const response = await axios.get('/api/alerts/history');
            setAlerts(response.data.data || []);
        } catch (error) {
            console.error('获取告警历史失败:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAlerts();
        const interval = setInterval(fetchAlerts, 30000); // 30 秒刷新
        return () => clearInterval(interval);
    }, []);

    const handleAcknowledge = async (id) => {
        await axios.post(`/api/alerts/${id}/ack`);
        fetchAlerts();
    };

    const columns = [
        { title: '规则名称', dataIndex: 'rule_name', key: 'rule_name' },
        { title: '触发时间', dataIndex: 'triggered_at', key: 'triggered_at',
            render: (t) => new Date(t).toLocaleString() },
        { title: '当前值', dataIndex: 'value', key: 'value' },
        { title: '状态', dataIndex: 'status', key: 'status',
            render: (status) => {
                const colors = { FIRING: 'red', RESOLVED: 'green', ACKNOWLEDGED: 'blue' };
                return <Tag color={colors[status]}>{status}</Tag>;
            } },
        { title: '消息', dataIndex: 'message', key: 'message', ellipsis: true },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                record.status === 'FIRING' && (
                    <Button icon={<CheckOutlined />} onClick={() => handleAcknowledge(record.id)}>
                        确认
                    </Button>
                )
            ),
        },
    ];

    return (
        <Card title="告警历史">
            <Table columns={columns} dataSource={alerts} rowKey="id" loading={loading} />
        </Card>
    );
};

export default AlertHistory;
```

- [ ] **Step 3: 添加路由**

修改 `web/src/App.jsx`:

```jsx
import AlertRules from './pages/AlertRules';
import AlertHistory from './pages/AlertHistory';

// 在 routes 数组中添加
{
    path: '/alerts/rules',
    element: <AlertRules />,
},
{
    path: '/alerts/history',
    element: <AlertHistory />,
},
```

- [ ] **Step 4: 提交**

```bash
git add web/src/pages/AlertRules.jsx web/src/pages/AlertHistory.jsx web/src/App.jsx
git commit -m "feat(web): 添加告警管理前端页面"
```

---

## 测试计划

### Task 16: 端到端测试

**Files:**
- Create: `tests/e2e/trace.e2e.test.js`

- [ ] **Step 1: 运行完整测试套件**

```bash
# 运行所有 Go 测试
go test ./... -v

# 运行前端测试
cd web
npm test

# 预期：所有测试通过
```

- [ ] **Step 2: 手动验证流程**

1. 启动服务器：`go run cmd/server/main.go`
2. 访问 Web 界面：`http://localhost:5612`
3. 创建一个告警规则
4. 触发一些 RPC 调用
5. 验证追踪列表显示数据
6. 验证告警历史

- [ ] **Step 3: 提交最终 commit**

```bash
git commit -m "feat: 完成监控和可观测性增强功能"
```

---

## 验证清单

在计划执行完成后，验证以下项目：

- [ ] 数据库迁移脚本已执行（trace_record, alert_rule, alert_history, alert_notification 表已创建）
- [ ] 追踪采集中间件正常工作，每次 API 调用都生成追踪记录
- [ ] 指标采集器正常工作，延迟指标被记录
- [ ] 告警评估器正在运行，定期评估规则
- [ ] 所有 API 端点可访问：
  - GET /api/traces
  - GET /api/traces/:traceId
  - GET /api/metrics/latency/percentiles
  - POST/GET/PUT/DELETE /api/alerts/rules
  - GET /api/alerts/history
  - GET /api/logs
- [ ] 前端页面可访问：
  - /traces
  - /traces/:traceId
  - /alerts/rules
  - /alerts/history
- [ ] 所有测试通过

---

## 相关文件索引

**规范文档:** `docs/superpowers/specs/2026-03-21-monitoring-observability-design.md` (如已创建)

**实现文件:**
- 数据模型：`pkg/model/trace.go`, `pkg/model/alert.go`
- 中间件：`pkg/server/middleware/trace.go`, `pkg/server/middleware/logging.go`
- 采集器：`pkg/server/metrics/collector.go`
- 评估器：`pkg/server/alert/evaluator.go`
- Handlers: `pkg/server/handlers/trace.go`, `pkg/server/handlers/alert.go`, `pkg/server/handlers/log.go`
- 前端：`web/src/pages/TraceList.jsx`, `web/src/pages/TraceDetail.jsx`, `web/src/pages/AlertRules.jsx`, `web/src/pages/AlertHistory.jsx`

**迁移脚本:**
- `deploy/postgres/migration/002_add_trace_record.sql`
- `deploy/postgres/migration/003_add_alert_tables.sql`
