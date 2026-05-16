package handlers

import (
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
)

// MetricHandler 监控指标处理器
type MetricHandler struct {
	metricRepo repository.MetricRepository
}

// NewMetricHandler 创建监控指标处理器
func NewMetricHandler(metricRepo repository.MetricRepository) *MetricHandler {
	return &MetricHandler{metricRepo: metricRepo}
}

// MetricDataVO 指标数据 VO
type MetricDataVO struct {
	Name    string   `json:"name"`
	TimeKey string   `json:"timeKey"`
	TagsMD5 string   `json:"tagsMd5"`
	Type    string   `json:"type"`
	Value   float64  `json:"value"`
	Tags    []string `json:"tags"`
}

// GetMetricsRequest 获取指标请求
type GetMetricsRequest struct {
	Name      string `json:"name" form:"name"`
	TimeRange string `json:"timeRange" form:"timeRange"` // minutes, hours, days
	StartTime string `json:"startTime" form:"startTime"`
	EndTime   string `json:"endTime" form:"endTime"`
}

// GetMetrics 获取指标数据
func (h *MetricHandler) GetMetrics(c *gin.Context) {
	var req GetMetricsRequest
	if err := c.ShouldBindQuery(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	table := "metric_minute"
	switch req.TimeRange {
	case "hours":
		table = "metric_hour"
	case "days":
		table = "metric_day"
	}

	metrics, err := h.metricRepo.FindMetrics(table, req.Name, req.StartTime, req.EndTime, 100)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	var vos []MetricDataVO
	for _, m := range metrics {
		tags := []string{}
		if m.Tag1 != "" {
			tags = append(tags, m.Tag1)
		}
		if m.Tag2 != "" {
			tags = append(tags, m.Tag2)
		}
		if m.Tag3 != "" {
			tags = append(tags, m.Tag3)
		}
		if m.Tag4 != "" {
			tags = append(tags, m.Tag4)
		}
		if m.Tag5 != "" {
			tags = append(tags, m.Tag5)
		}

		vos = append(vos, MetricDataVO{
			Name:    m.Name,
			TimeKey: m.TimeKey,
			TagsMD5: m.TagsMD5,
			Type:    m.Type,
			Value:   m.Value,
			Tags:    tags,
		})
	}

	Success(c, vos)
}

// GetMetricList 获取指标列表
func (h *MetricHandler) GetMetricList(c *gin.Context) {
	tags, err := h.metricRepo.FindMetricTags()
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, tags)
}

// GetDashboardData 获取大盘数据
func (h *MetricHandler) GetDashboardData(c *gin.Context) {
	data, err := h.metricRepo.GetDashboardData()
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, gin.H{
			"totalCalls":    data.TotalCalls,
			"onlineDevices": data.OnlineDevices,
			"totalGroups":   data.TotalGroups,
			"totalUsers":    data.TotalUsers,
		})
}

// GetLatencyPercentiles 获取延迟百分位数（P50/P90/P99）
func (h *MetricHandler) GetLatencyPercentiles(c *gin.Context) {
	group := c.Query("group")
	api := c.Query("api")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")

	latencyMetrics, err := h.metricRepo.GetLatencyPercentiles(group, api, startTime, endTime)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	type LatencyStats struct {
		API   string  `json:"api"`
		Group string  `json:"group"`
		P50   float64 `json:"p50"`
		P90   float64 `json:"p90"`
		P99   float64 `json:"p99"`
	}

	apiStats := make(map[string]*LatencyStats)
	for _, m := range latencyMetrics {
		key := m.Tag1 + ":" + m.Tag2
		if _, ok := apiStats[key]; !ok {
			apiStats[key] = &LatencyStats{
				Group: m.Tag1,
				API:   m.Tag2,
			}
		}

		stats := apiStats[key]
		if strings.Contains(m.Name, ".p50") || strings.HasSuffix(m.Name, "_p50") {
			stats.P50 = m.Value
		} else if strings.Contains(m.Name, ".p90") || strings.HasSuffix(m.Name, "_p90") {
			stats.P90 = m.Value
		} else if strings.Contains(m.Name, ".p99") || strings.HasSuffix(m.Name, "_p99") {
			stats.P99 = m.Value
		}
	}

	var result []LatencyStats
	for _, stats := range apiStats {
		result = append(result, *stats)
	}

	Success(c, result)
}
