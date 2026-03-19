package handlers

import (
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"

	"github.com/gin-gonic/gin"
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

// GetSysLogs 获取系统日志列表
func (h *SysConfigHandler) GetSysLogs(c *gin.Context) {
	var logs []model.SysLog
	if err := database.GetDB().Order("create_time DESC").Limit(100).Find(&logs).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    logs,
	})
}
