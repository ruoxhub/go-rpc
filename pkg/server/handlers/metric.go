package handlers

import (
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// MetricHandler 监控指标处理器
type MetricHandler struct{}

// NewMetricHandler 创建监控指标处理器
func NewMetricHandler() *MetricHandler {
	return &MetricHandler{}
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
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	var metrics []model.MetricMinute
	table := "metric_minute"
	switch req.TimeRange {
	case "hours":
		table = "metric_hour"
	case "days":
		table = "metric_day"
	}

	query := database.GetDB().Table(table)
	if req.Name != "" {
		query = query.Where("name = ?", req.Name)
	}

	if err := query.Order("time_key DESC").Limit(100).Find(&metrics).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
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

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
	})
}

// GetMetricList 获取指标列表
func (h *MetricHandler) GetMetricList(c *gin.Context) {
	var metricTags []model.MetricTag
	if err := database.GetDB().Find(&metricTags).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    metricTags,
	})
}

// GetDashboardData 获取大盘数据
func (h *MetricHandler) GetDashboardData(c *gin.Context) {
	// 获取调用量统计
	var totalCalls int64
	database.GetDB().Table("metric_minute").Select("SUM(value)").Where("type = ?", "counter").Scan(&totalCalls)

	// 获取在线设备数
	var onlineDevices int64
	database.GetDB().Table("group_device").Where("last_active_time > ?", time.Now().Add(-5*time.Minute)).Count(&onlineDevices)

	// 获取分组总数
	var totalGroups int64
	database.GetDB().Table("group_config").Count(&totalGroups)

	// 获取用户总数
	var totalUsers int64
	database.GetDB().Table("user_info").Count(&totalUsers)

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data": gin.H{
			"totalCalls":    totalCalls,
			"onlineDevices": onlineDevices,
			"totalGroups":   totalGroups,
			"totalUsers":    totalUsers,
		},
	})
}

// GetLatencyPercentiles 获取延迟百分位数（P50/P90/P99）
// GET /api/metrics/latency/percentiles
func (h *MetricHandler) GetLatencyPercentiles(c *gin.Context) {
	group := c.Query("group")
	api := c.Query("api")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")

	// 构建查询
	query := database.GetDB().Table("metric_minute").Where("type = ?", "latency")

	if group != "" {
		query = query.Where("tag1 = ?", group)
	}
	if api != "" {
		query = query.Where("tag2 = ?", api)
	}
	if startTime != "" {
		query = query.Where("time_key >= ?", startTime)
	}
	if endTime != "" {
		query = query.Where("time_key <= ?", endTime)
	}

	// 获取 P50/P90/P99 指标
	var latencyMetrics []model.MetricMinute
	if err := query.Where("name LIKE ? OR name LIKE ? OR name LIKE ?", "%.p%", "%_p%", "%.latency").Find(&latencyMetrics).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 按 API 分组
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

		// 从 name 中提取百分位数并赋值，如 "invoke.latency.p50" -> p50
		stats := apiStats[key]
		if strings.Contains(m.Name, ".p50") || strings.HasSuffix(m.Name, "_p50") {
			stats.P50 = m.Value
		} else if strings.Contains(m.Name, ".p90") || strings.HasSuffix(m.Name, "_p90") {
			stats.P90 = m.Value
		} else if strings.Contains(m.Name, ".p99") || strings.HasSuffix(m.Name, "_p99") {
			stats.P99 = m.Value
		}
	}

	// 转换为数组
	var result []LatencyStats
	for _, stats := range apiStats {
		result = append(result, *stats)
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    result,
	})
}
