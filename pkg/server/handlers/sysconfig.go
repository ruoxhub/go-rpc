package handlers

import (
	"fmt"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
)

// SysConfigHandler 系统配置处理器
type SysConfigHandler struct{}

// NewSysConfigHandler 创建系统配置处理器
func NewSysConfigHandler() *SysConfigHandler {
	return &SysConfigHandler{}
}

// ConfigVO 配置项 VO
type ConfigVO struct {
	Key   string `json:"key"`
	Label string `json:"label"`
	Value string `json:"value"`
}

// List 获取系统配置列表
func (h *SysConfigHandler) List(c *gin.Context) {
	var configs []model.SysConfig
	if err := database.GetDB().Find(&configs).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 配置项中文标签映射
	labelMap := map[string]string{
		"sekiro.user.allowRegister":           "是否允许注册用户",
		"sekiro.outIpTestUrl":                 "出口 ip 探测 URL",
		"sekiro.systemNotice":                 "系统通告信息",
		"sekiro.docNotice":                    "文档首页通告信息",
		"sekiro.allowAnonymousAccess":         "是否允许匿名访问",
		"sekiro.anonymousAccessRateLimit":     "匿名访问 qps 限制",
		"sekiro.defaultRegisterQuotaUser":     "注册用户默认 qps 限制",
		"sekiro.defaultRegisterQuotaGroup":    "注册 group 默认 qps 限制",
		"sekiro.useCustomSSLCertificate":      "使用自定义 ssl 证书",
		"sekiro.autoGenSSLCertificateHostList": "为配置的 host 自动生成 ssl 证书",
		"sekiro.open443Website":               "开启 443 服务端口",
		"sekiro.defendIdleInvoke":             "空转调用保护",
	}

	var vos []ConfigVO
	for _, cfg := range configs {
		label := labelMap[cfg.ConfigKey]
		if label == "" {
			label = cfg.ConfigKey
		}
		vos = append(vos, ConfigVO{
			Key:   cfg.ConfigKey,
			Label: label,
			Value: cfg.ConfigValue,
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
	})
}

// UpdateConfigRequest 更新配置请求
type UpdateConfigRequest struct {
	Key   string `json:"key" binding:"required"`
	Value string `json:"value" binding:"required"`
}

// Update 更新系统配置
func (h *SysConfigHandler) Update(c *gin.Context) {
	var req UpdateConfigRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	if err := database.GetDB().Model(&model.SysConfig{}).
		Where("config_key = ?", req.Key).
		Update("config_value", req.Value).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

// GetServerNodes 获取服务器节点列表
func (h *SysConfigHandler) GetServerNodes(c *gin.Context) {
	var nodes []model.ServerNode
	if err := database.GetDB().Find(&nodes).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    nodes,
	})
}

// GetSysLogs 获取系统日志列表（增强版）
// GET /api/sysconfig/logs
// 支持过滤：level, startTime, endTime, keyword, page, pageSize
func (h *SysConfigHandler) GetSysLogs(c *gin.Context) {
	// 获取查询参数
	level := c.Query("level")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")
	keyword := c.Query("keyword")
	page := c.DefaultQuery("page", "1")
	pageSize := c.DefaultQuery("pageSize", "20")

	// 解析分页参数
	var pageInt, pageSizeInt int
	fmt.Sscanf(page, "%d", &pageInt)
	fmt.Sscanf(pageSize, "%d", &pageSizeInt)
	if pageInt <= 0 {
		pageInt = 1
	}
	if pageSizeInt <= 0 {
		pageSizeInt = 20
	}

	// 构建查询
	query := database.GetDB().Table("sys_log")

	// 按级别过滤
	if level != "" {
		query = query.Where("level = ?", level)
	}

	// 按时间范围过滤
	if startTime != "" {
		query = query.Where("create_time >= ?", startTime)
	}
	if endTime != "" {
		query = query.Where("create_time <= ?", endTime)
	}

	// 按关键词搜索（消息内容）
	if keyword != "" {
		query = query.Where("message LIKE ? OR detail LIKE ?", "%"+keyword+"%", "%"+keyword+"%")
	}

	// 获取总数
	var total int64
	query.Count(&total)

	// 分页
	offset := (pageInt - 1) * pageSizeInt
	query = query.Offset(offset).Limit(pageSizeInt).Order("create_time DESC")

	var logs []model.SysLog
	if err := query.Find(&logs).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    logs,
		"total":   total,
		"page":    pageInt,
		"pageSize": pageSizeInt,
	})
}

// GetAppLogs 获取应用日志列表（最近的文件日志）
// GET /api/sysconfig/app-logs
// 支持过滤：level, traceId, group, startTime, endTime, page, pageSize
func (h *SysConfigHandler) GetAppLogs(c *gin.Context) {
	// 获取查询参数
	level := c.Query("level")
	traceId := c.Query("traceId")
	group := c.Query("group")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")
	page := c.DefaultQuery("page", "1")
	pageSize := c.DefaultQuery("pageSize", "50")

	// 解析分页参数
	var pageInt, pageSizeInt int
	fmt.Sscanf(page, "%d", &pageInt)
	fmt.Sscanf(pageSize, "%d", &pageSizeInt)
	if pageInt <= 0 {
		pageInt = 1
	}
	if pageSizeInt <= 0 {
		pageSizeInt = 50
	}

	// 构建查询（从 metric_minute 模拟查询日志，实际应该读日志文件）
	// 这里返回一个示例结构，实际应该读取并解析 JSON 日志文件
	type AppLogEntry struct {
		Timestamp string `json:"timestamp"`
		Level     string `json:"level"`
		Message   string `json:"message"`
		TraceID   string `json:"trace_id,omitempty"`
		Group     string `json:"group,omitempty"`
		Duration  string `json:"duration_ms,omitempty"`
		Status    int    `json:"status,omitempty"`
	}

	// 模拟返回最近的请求日志（从 trace_record 查询）
	var logs []AppLogEntry
	dbQuery := database.GetDB().Table("trace_record").
		Select("start_time as timestamp, 'INFO' as level, api as message, trace_id, \"group\", duration_ms, CASE WHEN status='SUCCESS' THEN 200 ELSE 500 END as status")

	if level != "" {
		// 简化处理：级别过滤暂不实现
	}
	if traceId != "" {
		dbQuery = dbQuery.Where("trace_id = ?", traceId)
	}
	if group != "" {
		dbQuery = dbQuery.Where("\"group\" = ?", group)
	}
	if startTime != "" {
		dbQuery = dbQuery.Where("start_time >= ?", startTime)
	}
	if endTime != "" {
		dbQuery = dbQuery.Where("start_time <= ?", endTime)
	}

	offset := (pageInt - 1) * pageSizeInt
	dbQuery = dbQuery.Offset(offset).Limit(pageSizeInt).Order("start_time DESC")

	if err := dbQuery.Scan(&logs).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":     0,
		"message":  "success",
		"data":     logs,
		"total":    len(logs),
		"page":     pageInt,
		"pageSize": pageSizeInt,
	})
}
