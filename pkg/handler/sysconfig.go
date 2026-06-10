package handler

import (
	"fmt"

	"github.com/gin-gonic/gin"
	pkgconfig "github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
)

// SysConfigHandler 系统配置处理器
type SysConfigHandler struct {
	sysConfigRepo  repository.SysConfigRepository
	serverNodeRepo repository.ServerNodeRepository
	sysLogRepo     repository.SysLogRepository
	configService  pkgconfig.Service
}

// NewSysConfigHandler 创建系统配置处理器
func NewSysConfigHandler(
	sysConfigRepo repository.SysConfigRepository,
	serverNodeRepo repository.ServerNodeRepository,
	sysLogRepo repository.SysLogRepository,
	service pkgconfig.Service,
) *SysConfigHandler {
	return &SysConfigHandler{
		sysConfigRepo:  sysConfigRepo,
		serverNodeRepo: serverNodeRepo,
		sysLogRepo:     sysLogRepo,
		configService:  service,
	}
}

// ConfigVO 配置项 VO
type ConfigVO struct {
	Key   string `json:"key"`
	Label string `json:"label"`
	Value string `json:"value"`
}

// List 获取系统配置列表
func (h *SysConfigHandler) List(c *gin.Context) {
	configs, err := h.sysConfigRepo.FindAll()
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	labelMap := map[string]string{
		"sekiro.user.allowRegister":            "是否允许注册用户",
		"sekiro.outIpTestUrl":                  "出口 ip 探测 URL",
		"sekiro.systemNotice":                  "系统通告信息",
		"sekiro.docNotice":                     "文档首页通告信息",
		"sekiro.allowAnonymousAccess":          "是否允许匿名访问",
		"sekiro.anonymousAccessRateLimit":      "匿名访问 qps 限制",
		"sekiro.defaultRegisterQuotaUser":      "注册用户默认 qps 限制",
		"sekiro.defaultRegisterQuotaGroup":     "注册 group 默认 qps 限制",
		"sekiro.useCustomSSLCertificate":       "使用自定义 ssl 证书",
		"sekiro.autoGenSSLCertificateHostList": "为配置的 host 自动生成 ssl 证书",
		"sekiro.open443Website":                "开启 443 服务端口",
		"sekiro.defendIdleInvoke":              "空转调用保护",
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

	Success(c, vos)
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
		BadRequest(c, err.Error())
		return
	}

	if err := h.sysConfigRepo.Upsert(req.Key, req.Value); err != nil {
		InternalError(c, err.Error())
		return
	}

	if h.configService != nil {
		if err := h.configService.Refresh(); err != nil {
			InternalError(c, "配置已保存，但刷新失败："+err.Error())
			return
		}
	}

	auditUpdateConfig(c, req.Key, req.Value)
	Success(c, nil)
}

// GetServerNodes 获取服务器节点列表
func (h *SysConfigHandler) GetServerNodes(c *gin.Context) {
	nodes, err := h.serverNodeRepo.FindAll()
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, nodes)
}

// parsePagination parses page and pageSize query parameters with defaults.
func parsePagination(c *gin.Context, defaultPageSize int) (page, pageSize int) {
	pageStr := c.DefaultQuery("page", "1")
	sizeStr := c.DefaultQuery("pageSize", fmt.Sprintf("%d", defaultPageSize))

	fmt.Sscanf(pageStr, "%d", &page)
	fmt.Sscanf(sizeStr, "%d", &pageSize)
	if page <= 0 {
		page = 1
	}
	if pageSize <= 0 {
		pageSize = defaultPageSize
	}
	return
}

// GetSysLogs 获取系统日志列表
func (h *SysConfigHandler) GetSysLogs(c *gin.Context) {
	level := c.Query("level")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")
	keyword := c.Query("keyword")
	page, pageSize := parsePagination(c, 20)

	logs, total, err := h.sysLogRepo.FindAll(repository.SysLogQuery{
		Level:     level,
		StartTime: startTime,
		EndTime:   endTime,
		Keyword:   keyword,
		Page:      page,
		PageSize:  pageSize,
	})
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	c.JSON(200, gin.H{
		"code":     0,
		"message":  "success",
		"data":     logs,
		"total":    total,
		"page":     page,
		"pageSize": pageSize,
	})
}

// GetAppLogs 获取应用日志列表（最近的文件日志）
func (h *SysConfigHandler) GetAppLogs(c *gin.Context) {
	level := c.Query("level")
	traceId := c.Query("traceId")
	group := c.Query("group")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")
	page, pageSize := parsePagination(c, 50)

	type AppLogEntry struct {
		Timestamp string `json:"timestamp"`
		Level     string `json:"level"`
		Message   string `json:"message"`
		TraceID   string `json:"trace_id,omitempty"`
		Group     string `json:"group,omitempty"`
		Duration  string `json:"duration_ms,omitempty"`
		Status    int    `json:"status,omitempty"`
	}

	_ = level // level filtering not implemented for app logs

	var logs []AppLogEntry
	// This is a complex analytics query spanning trace_record;
	// use the global DB instance directly.
	db := repository.GetDB()
	rawQuery := db.Table("trace_record").
		Select("start_time as timestamp, 'INFO' as level, api as message, trace_id, \"group\", duration_ms, CASE WHEN status='SUCCESS' THEN 200 ELSE 500 END as status")

	if traceId != "" {
		rawQuery = rawQuery.Where("trace_id = ?", traceId)
	}
	if group != "" {
		rawQuery = rawQuery.Where(`"group" = ?`, group)
	}
	if startTime != "" {
		rawQuery = rawQuery.Where("start_time >= ?", startTime)
	}
	if endTime != "" {
		rawQuery = rawQuery.Where("start_time <= ?", endTime)
	}

	offset := (page - 1) * pageSize
	if err := rawQuery.Offset(offset).Limit(pageSize).Order("start_time DESC").Scan(&logs).Error; err != nil {
		InternalError(c, err.Error())
		return
	}

	c.JSON(200, gin.H{
		"code":     0,
		"message":  "success",
		"data":     logs,
		"total":    len(logs),
		"page":     page,
		"pageSize": pageSize,
	})
}
