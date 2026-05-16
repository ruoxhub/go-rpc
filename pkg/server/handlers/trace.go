package handlers

import (
	"encoding/json"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// TraceHandler 追踪查询处理器
type TraceHandler struct {
	traceRepo repository.TraceRepository
}

// NewTraceHandler 创建追踪查询处理器
func NewTraceHandler(traceRepo repository.TraceRepository) *TraceHandler {
	return &TraceHandler{traceRepo: traceRepo}
}

// GetTraces 获取追踪列表
func (h *TraceHandler) GetTraces(c *gin.Context) {
	var query model.TraceQuery
	if err := c.ShouldBindQuery(&query); err != nil {
		BadRequest(c, err.Error())
		return
	}

	records, total, err := h.traceRepo.FindByQuery(query)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	SuccessWithTotal(c, records, total)
}

// GetTraceDetail 获取追踪详情（包含完整链路）
func (h *TraceHandler) GetTraceDetail(c *gin.Context) {
	traceID := c.Param("traceId")

	records, err := h.traceRepo.FindByTraceID(traceID)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	if len(records) == 0 {
		NotFound(c, "追踪记录不存在")
		return
	}

	Success(c, gin.H{
			"trace_id": traceID,
			"spans":    records,
		})
}

// GetTraceStats 获取追踪统计信息
func (h *TraceHandler) GetTraceStats(c *gin.Context) {
	group := c.Query("group")
	api := c.Query("api")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")

	stats, err := h.traceRepo.GetStats(group, api, startTime, endTime)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, gin.H{
			"total":        stats.Total,
			"successCount": stats.SuccessCount,
			"failureCount": stats.FailureCount,
			"successRate":  stats.SuccessRate,
			"avgLatency":   stats.AvgLatency,
			"maxLatency":   stats.MaxLatency,
			"minLatency":   stats.MinLatency,
		})
}

// GetTraceTimeline 获取追踪时间线数据（用于图表）
func (h *TraceHandler) GetTraceTimeline(c *gin.Context) {
	group := c.Query("group")
	api := c.Query("api")

	records, err := h.traceRepo.GetTimeline(group, api, 100)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

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

	var stats []MinuteStat
	for _, stat := range minuteStats {
		stats = append(stats, *stat)
	}

	Success(c, stats)
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

	record, err := h.traceRepo.FindFirstByTraceID(traceID)
	if err != nil {
		NotFound(c, "追踪记录不存在")
		return
	}

	var extraData ExtraDataVO
	if record.ExtraData != "" {
		json.Unmarshal([]byte(record.ExtraData), &extraData)
	}

	Success(c, extraData)
}
