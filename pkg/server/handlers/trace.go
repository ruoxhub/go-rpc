package handlers

import (
	"encoding/json"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
)

// TraceHandler 追踪查询处理器
type TraceHandler struct{}

// NewTraceHandler 创建追踪查询处理器
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
	if query.MinDuration > 0 {
		db = db.Where("duration_ms >= ?", query.MinDuration)
	}
	if query.MaxDuration > 0 {
		db = db.Where("duration_ms <= ?", query.MaxDuration)
	}

	// 获取总数
	var total int64
	db.Count(&total)

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

// GetTraceStats 获取追踪统计信息
func (h *TraceHandler) GetTraceStats(c *gin.Context) {
	group := c.Query("group")
	api := c.Query("api")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")

	// 构建查询
	query := database.GetDB().Table("trace_record")

	if group != "" {
		query = query.Where("\"group\" = ?", group)
	}
	if api != "" {
		query = query.Where("api LIKE ?", "%"+api+"%")
	}
	if startTime != "" {
		query = query.Where("start_time >= ?", startTime)
	}
	if endTime != "" {
		query = query.Where("start_time <= ?", endTime)
	}

	// 统计总数
	var total int64
	query.Count(&total)

	// 统计成功/失败数
	var successCount int64
	query.Where("status = ?", model.SpanStatusSuccess).Count(&successCount)

	var failureCount int64
	query.Where("status = ?", model.SpanStatusFailure).Count(&failureCount)

	// 平均延迟
	var avgLatency float64
	query.Select("AVG(duration_ms)").Scan(&avgLatency)

	// 最大延迟
	var maxLatency int64
	query.Select("MAX(duration_ms)").Scan(&maxLatency)

	// 最小延迟
	var minLatency int64
	query.Select("MIN(duration_ms)").Scan(&minLatency)

	successRate := 0.0
	if total > 0 {
		successRate = float64(successCount) / float64(total) * 100
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data": gin.H{
			"total":        total,
			"successCount": successCount,
			"failureCount": failureCount,
			"successRate":  successRate,
			"avgLatency":   avgLatency,
			"maxLatency":   maxLatency,
			"minLatency":   minLatency,
		},
	})
}

// GetTraceTimeline 获取追踪时间线数据（用于图表）
func (h *TraceHandler) GetTraceTimeline(c *gin.Context) {
	group := c.Query("group")
	api := c.Query("api")
	_ = c.DefaultQuery("duration", "1h") // 默认 1 小时

	// 构建查询
	query := database.GetDB().Table("trace_record")

	if group != "" {
		query = query.Where("\"group\" = ?", group)
	}
	if api != "" {
		query = query.Where("api LIKE ?", "%"+api+"%")
	}

	// 根据 duration 计算开始时间
	// 简化实现：查询最近 N 条记录
	var records []model.TraceRecord
	query.Order("start_time DESC").Limit(100).Find(&records)

	// 按分钟分组统计
	type MinuteStat struct {
		TimeKey string  `json:"timeKey"`
		Count   int64   `json:"count"`
		AvgMs   float64 `json:"avgMs"`
	}

	minuteStats := make(map[string]*MinuteStat)
	for _, r := range records {
		timeKey := r.StartTime.Format("2006-01-02 15:04")
		if stat, ok := minuteStats[timeKey]; ok {
			stat.Count++
			stat.AvgMs = (stat.AvgMs*float64(stat.Count-1) + float64(r.DurationMs)) / float64(stat.Count)
		} else {
			minuteStats[timeKey] = &MinuteStat{
				TimeKey: timeKey,
				Count:   1,
				AvgMs:   float64(r.DurationMs),
			}
		}
	}

	// 转换为数组
	var stats []MinuteStat
	for _, stat := range minuteStats {
		stats = append(stats, *stat)
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    stats,
	})
}

// ExtraDataVO 额外数据结构
type ExtraDataVO struct {
	Method      string `json:"method"`
	UserAgent   string `json:"user_agent"`
	ContentType string `json:"content_type"`
	StatusCode  int    `json:"status_code"`
	UserID      int64  `json:"user_id,omitempty"`
	UserName    string `json:"user_name,omitempty"`
}

// GetTraceExtraData 获取追踪额外数据
func (h *TraceHandler) GetTraceExtraData(c *gin.Context) {
	traceID := c.Param("traceId")

	var record model.TraceRecord
	if err := database.GetDB().Where("trace_id = ?", traceID).First(&record).Error; err != nil {
		c.JSON(404, gin.H{"code": 404, "message": "追踪记录不存在"})
		return
	}

	var extraData ExtraDataVO
	if record.ExtraData != "" {
		json.Unmarshal([]byte(record.ExtraData), &extraData)
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    extraData,
	})
}
