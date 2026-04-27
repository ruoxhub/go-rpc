package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	pkgconfig "github.com/sekiro-go/sekiro-go/pkg/server/config"
)

// AnonymousGroupHandler 匿名分组处理器
type AnonymousGroupHandler struct{}

// NewAnonymousGroupHandler 创建匿名分组处理器
func NewAnonymousGroupHandler() *AnonymousGroupHandler {
	return &AnonymousGroupHandler{}
}

// AnonymousGroupVO 匿名分组 VO
type AnonymousGroupVO struct {
	GroupName        string `json:"groupName"`
	AvailableClients int64  `json:"availableClients"`
	DisabledClients  int64  `json:"disabledClients"`
	TotalClients     int64  `json:"totalClients"`
}

// List 获取匿名分组列表
// 匿名分组定义：存在于 group_device 表中，但其 group_name 不在 group_config 表中的设备
func (h *AnonymousGroupHandler) List(c *gin.Context) {
	db := database.GetDB()

	// 子查询：获取所有已注册分组的 group_name
	// 然后查询不在这个列表中的设备，按 group_name 分组统计
	var devices []struct {
		GroupName      string    `json:"group_name"`
		LastActiveTime time.Time `json:"last_active_time"`
	}

	// 查询所有设备，其 group_name 不在 group_config 表中
	if err := db.Table("group_device gd").
		Where("NOT EXISTS (SELECT 1 FROM group_config gc WHERE gc.group_name = gd.group_name)").
		Find(&devices).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 如果没有任何匿名设备，直接返回空数组
	if len(devices) == 0 {
		c.JSON(200, gin.H{
			"code":    0,
			"message": "success",
			"data":    []AnonymousGroupVO{},
		})
		return
	}

	// 按 group_name 分组统计
	groupMap := make(map[string][]time.Time)
	for _, d := range devices {
		groupMap[d.GroupName] = append(groupMap[d.GroupName], d.LastActiveTime)
	}

	// 预计算时间阈值，避免多次计算
	activeThreshold := time.Now().Add(-ClientInactiveThreshold)

	// 构建结果
	var vos []AnonymousGroupVO
	for groupName, activeTimes := range groupMap {
		var availableCount, disabledCount int64
		for _, activeTime := range activeTimes {
			if activeTime.After(activeThreshold) {
				availableCount++
			} else {
				disabledCount++
			}
		}

		vos = append(vos, AnonymousGroupVO{
			GroupName:        groupName,
			AvailableClients: availableCount,
			DisabledClients:  disabledCount,
			TotalClients:     availableCount + disabledCount,
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
	})
}

// ListOptimized 优化版本：使用数据库聚合查询
func (h *AnonymousGroupHandler) ListOptimized(c *gin.Context) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return
	}
	if !user.IsAdmin {
		c.JSON(403, gin.H{"code": 403, "message": "需要管理员权限"})
		return
	}

	db := database.GetDB()

	// 使用 SQL 直接分组统计
	type GroupStats struct {
		GroupName string `json:"group_name"`
		Total     int64  `json:"total"`
		ActiveSQL string `json:"-"` // 用于计算活跃数
	}

	// 查询匿名分组的统计信息
	// 活跃：last_active_time > 5 分钟前
	// 禁用：last_active_time <= 5 分钟前
	activeThreshold := time.Now().Add(-ClientInactiveThreshold)

	var stats []struct {
		GroupName string `json:"group_name"`
		Total     int64  `json:"total"`
		Active    int64  `json:"active"`
		Disabled  int64  `json:"disabled"`
	}

	// 使用 CASE WHEN 在 SQL 层面计算活跃/禁用数量
	if err := db.Table("group_device gd").
		Select(`
			gd.group_name,
			COUNT(*) as total,
			SUM(CASE WHEN gd.last_active_time > ? THEN 1 ELSE 0 END) as active,
			SUM(CASE WHEN gd.last_active_time <= ? THEN 1 ELSE 0 END) as disabled
		`, activeThreshold, activeThreshold).
		Where("NOT EXISTS (SELECT 1 FROM group_config gc WHERE gc.group_name = gd.group_name)").
		Group("gd.group_name").
		Find(&stats).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 如果没有任何匿名设备，直接返回空数组
	if len(stats) == 0 {
		c.JSON(200, gin.H{
			"code":    0,
			"message": "success",
			"data":    []AnonymousGroupVO{},
		})
		return
	}

	// 构建结果
	vos := make([]AnonymousGroupVO, len(stats))
	for i, s := range stats {
		vos[i] = AnonymousGroupVO{
			GroupName:        s.GroupName,
			AvailableClients: s.Active,
			DisabledClients:  s.Disabled,
			TotalClients:     s.Total,
		}
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
	})
}

// DeleteAnonymousGroupRequest 删除匿名分组请求
type DeleteAnonymousGroupRequest struct {
	GroupName string `json:"groupName" binding:"required"`
}

// Delete 删除匿名分组
// 注意：匿名分组没有对应的 group_config 记录，只需要删除 group_device 表中的记录
func (h *AnonymousGroupHandler) Delete(c *gin.Context) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return
	}
	if !user.IsAdmin {
		c.JSON(403, gin.H{"code": 403, "message": "需要管理员权限"})
		return
	}

	var req DeleteAnonymousGroupRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 检查是否是匿名分组（即不存在于 group_config 表中）
	var groupCount int64
	if err := database.GetDB().Model(&model.GroupConfig{}).
		Where("group_name = ?", req.GroupName).
		Count(&groupCount).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	if groupCount > 0 {
		c.JSON(400, gin.H{
			"code":    400,
			"message": "不能删除已注册的分组，请在分组管理中删除",
		})
		return
	}

	// 删除匿名分组的所有设备记录
	result := database.GetDB().Where("group_name = ?", req.GroupName).
		Delete(&model.GroupDevice{})

	if result.Error != nil {
		c.JSON(500, gin.H{"code": 500, "message": result.Error.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    result.RowsAffected,
	})
}

// ConvertAnonymousGroupRequest 转换匿名分组请求
type ConvertAnonymousGroupRequest struct {
	GroupName         string  `json:"groupName" binding:"required"`
	QuotaQpsGroup     float64 `json:"quotaQpsGroup"`
	QuotaQpsPerDevice float64 `json:"quotaQpsPerDevice"`
}

// ConvertAnonymousGroup 将匿名分组转换为正式分组
// POST /api/anonymous-groups/convert
func (h *AnonymousGroupHandler) ConvertAnonymousGroup(c *gin.Context) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return
	}
	if !user.IsAdmin {
		c.JSON(403, gin.H{"code": 403, "message": "需要管理员权限"})
		return
	}

	var req ConvertAnonymousGroupRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 检查是否是匿名分组（即不存在于 group_config 表中）
	var groupCount int64
	if err := database.GetDB().Model(&model.GroupConfig{}).
		Where("group_name = ?", req.GroupName).
		Count(&groupCount).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	if groupCount > 0 {
		c.JSON(400, gin.H{
			"code":    400,
			"message": "该分组已是正式分组，无需转换",
		})
		return
	}

	// 从认证中间件获取当前用户信息
	// 获取默认 QPS 配置
	var defaultGroupQps float64 = 100
	var defaultDeviceQps float64 = 10
	cfgSvc, cfgExists := c.Get("configService")
	if cfgExists {
		if configSvc, ok := cfgSvc.(pkgconfig.Service); ok {
			defaultGroupQps = configSvc.GetConfigFloat(pkgconfig.ConfigKeyDefaultQuotaGroup, 100.0)
			defaultDeviceQps = configSvc.GetConfigFloat(pkgconfig.ConfigKeyDefaultQuotaPerDevice, 10.0)
		}
	}

	// 创建分组配置（事务中）
	tx := database.GetDB().Begin()

	group := model.GroupConfig{
		GroupName:         req.GroupName,
		UserName:          user.UserName,
		QuotaQpsGroup:     req.QuotaQpsGroup,
		QuotaQpsPerDevice: req.QuotaQpsPerDevice,
		CreateDate:        time.Now(),
	}

	// 如果用户未指定 QPS，使用默认值
	if group.QuotaQpsGroup <= 0 {
		group.QuotaQpsGroup = defaultGroupQps
	}
	if group.QuotaQpsPerDevice <= 0 {
		group.QuotaQpsPerDevice = defaultDeviceQps
	}

	if err := tx.Create(&group).Error; err != nil {
		tx.Rollback()
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 为该分组自动添加默认 Actions
	for _, actionName := range DefaultGroupActions {
		var actionCount int64
		if err := tx.Model(&model.GroupAction{}).
			Where("group_name = ? AND action_name = ?", req.GroupName, actionName).
			Count(&actionCount).Error; err != nil {
			logger.Warnf("Failed to check action existence: group=%s, action=%s, err=%v", req.GroupName, actionName, err)
			continue
		}

		if actionCount == 0 {
			action := model.GroupAction{
				GroupName:  req.GroupName,
				ActionName: actionName,
				CreateDate: time.Now(),
			}
			if err := tx.Create(&action).Error; err != nil {
				logger.Warnf("Failed to create default action: group=%s, action=%s, err=%v", req.GroupName, actionName, err)
			} else {
				logger.Infof("Default action created during conversion: group=%s, action=%s", req.GroupName, actionName)
			}
		}
	}

	tx.Commit()

	// 记录审计日志
	auditConvertGroup(c, "anonymous:"+req.GroupName, req.GroupName)

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    group.ID,
	})
}
