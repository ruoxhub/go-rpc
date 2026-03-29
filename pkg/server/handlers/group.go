package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"github.com/sekiro-go/sekiro-go/pkg/server/config"
	"github.com/sekiro-go/sekiro-go/pkg/server/middleware"
)

// GroupHandler 分组管理处理器
type GroupHandler struct{}

// NewGroupHandler 创建分组处理器
func NewGroupHandler() *GroupHandler {
	return &GroupHandler{}
}

// GroupListResponse 分组列表响应
type GroupListResponse struct {
	Code    int           `json:"code"`
	Message string        `json:"message"`
	Data    []GroupInfoVO `json:"data"`
	Total   int64         `json:"total"`
}

type GroupInfoVO struct {
	ID                int64   `json:"id"`
	GroupName         string  `json:"groupName"`
	UserName          string  `json:"userName"`
	QuotaQpsGroup     float64 `json:"quotaQpsGroup"`
	QuotaQpsPerDevice float64 `json:"quotaQpsPerDevice"`
	CreateTime        string  `json:"createTime"`
	AvailableClients  int64   `json:"availableClients"`
	DisabledClients   int64   `json:"disabledClients"`
	// 兼容旧版字段
	AvailableClientSize int64 `json:"availableClientSize"`
	DisableClientSize   int64 `json:"disableClientSize"`
}

// List 获取分组列表
func (h *GroupHandler) List(c *gin.Context) {
	db := database.GetDB()

	// 优化版本：使用单次 JOIN + GROUP BY 查询替代 N+1 查询
	// 查询所有分组及其设备统计信息
	activeThreshold := time.Now().Add(-ClientInactiveThreshold)

	var stats []GroupStats
	err := db.Table("group_config gc").
		Select(`
			gc.id,
			gc.group_name,
			gc.user_name,
			gc.quota_qps_group,
			gc.quota_qps_per_device,
			gc.create_date,
			COUNT(gd.id) as total_clients,
			SUM(CASE WHEN gd.last_active_time > ? THEN 1 ELSE 0 END) as available_clients,
			SUM(CASE WHEN gd.last_active_time <= ? THEN 1 ELSE 0 END) as disabled_clients
		`, activeThreshold, activeThreshold).
		Joins("LEFT JOIN group_device gd ON gc.group_name = gd.group_name").
		Group("gc.id, gc.group_name, gc.user_name, gc.quota_qps_group, gc.quota_qps_per_device, gc.create_date").
		Order("gc.create_date DESC").
		Scan(&stats).Error

	if err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 构建响应 VO
	vos := make([]GroupInfoVO, 0, len(stats))
	for _, s := range stats {
		vos = append(vos, GroupInfoVO{
			ID:                s.ID,
			GroupName:         s.GroupName,
			UserName:          s.UserName,
			QuotaQpsGroup:     s.QuotaQpsGroup,
			QuotaQpsPerDevice: s.QuotaQpsPerDevice,
			CreateTime:        s.CreateDate.Format("2006-01-02 15:04:05"),
			AvailableClients:  s.AvailableClients,
			DisabledClients:   s.DisabledClients,
			// 兼容旧版字段
			AvailableClientSize: s.AvailableClients,
			DisableClientSize:   s.DisabledClients,
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
		"total":   int64(len(vos)),
	})
}

// GroupStats 分组统计信息 (内部使用)
type GroupStats struct {
	ID                int64
	GroupName         string
	UserName          string
	QuotaQpsGroup     float64
	QuotaQpsPerDevice float64
	CreateDate        time.Time
	TotalClients      int64
	AvailableClients  int64
	DisabledClients   int64
}

// CreateGroupRequest 创建分组请求
type CreateGroupRequest struct {
	GroupName         string  `json:"groupName" binding:"required"`
	QuotaQpsGroup     float64 `json:"quotaQpsGroup"`
	QuotaQpsPerDevice float64 `json:"quotaQpsPerDevice"`
}

// Create 创建分组
func (h *GroupHandler) Create(c *gin.Context) {
	var req CreateGroupRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 从认证中间件获取当前用户信息
	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		c.JSON(401, gin.H{"code": 401, "message": "请先登录"})
		return
	}

	// 获取默认 QPS 配置
	var defaultGroupQps float64 = 100
	var defaultDeviceQps float64 = 10
	cfgSvc, cfgExists := c.Get("configService")
	if cfgExists {
		if configSvc, ok := cfgSvc.(config.Service); ok {
			defaultGroupQps = configSvc.GetConfigFloat(config.ConfigKeyDefaultQuotaGroup, 100.0)
			defaultDeviceQps = configSvc.GetConfigFloat(config.ConfigKeyDefaultQuotaPerDevice, 10.0)
		}
	}

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

	if err := database.GetDB().Create(&group).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success", "data": group.ID})
}

// DeleteGroupRequest 删除分组请求
type DeleteGroupRequest struct {
	GroupName string `json:"groupName" binding:"required"`
}

// Delete 删除分组
func (h *GroupHandler) Delete(c *gin.Context) {
	var req DeleteGroupRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	tx := database.GetDB().Begin()

	// 先删除关联的设备和 action
	if err := tx.Where("group_name = ?", req.GroupName).Delete(&model.GroupDevice{}).Error; err != nil {
		tx.Rollback()
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}
	if err := tx.Where("group_name = ?", req.GroupName).Delete(&model.GroupAction{}).Error; err != nil {
		tx.Rollback()
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}
	// 删除分组
	if err := tx.Where("group_name = ?", req.GroupName).Delete(&model.GroupConfig{}).Error; err != nil {
		tx.Rollback()
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	tx.Commit()
	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

// GetGroupDetail 获取分组详情
func (h *GroupHandler) GetDetail(c *gin.Context) {
	groupName := c.Param("groupName")

	var group model.GroupConfig
	if err := database.GetDB().Where("group_name = ?", groupName).First(&group).Error; err != nil {
		c.JSON(404, gin.H{"code": 404, "message": "group not found"})
		return
	}

	// 优化版本：使用单次查询同时统计活跃和禁用设备数量
	activeThreshold := time.Now().Add(-ClientInactiveThreshold)

	var stats struct {
		Available int64 `json:"available"`
		Disabled  int64 `json:"disabled"`
	}

	err := database.GetDB().Model(&model.GroupDevice{}).
		Select(`
			SUM(CASE WHEN last_active_time > ? THEN 1 ELSE 0 END) as available,
			SUM(CASE WHEN last_active_time <= ? THEN 1 ELSE 0 END) as disabled
		`, activeThreshold, activeThreshold).
		Where("group_name = ?", groupName).
		Scan(&stats).Error

	if err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data": gin.H{
			"groupName":         group.GroupName,
			"userName":          group.UserName,
			"createTime":        group.CreateDate.Format("2006-01-02 15:04:05"),
			"quotaQpsGroup":     group.QuotaQpsGroup,
			"quotaQpsPerDevice": group.QuotaQpsPerDevice,
			"availableClients":  stats.Available,
			"disabledClients":   stats.Disabled,
		},
	})
}

// UpdateGroupQpsRequest 更新分组 QPS 请求
type UpdateGroupQpsRequest struct {
	GroupName         string  `json:"groupName" binding:"required"`
	QuotaQpsGroup     float64 `json:"quotaQpsGroup"`
	QuotaQpsPerDevice float64 `json:"quotaQpsPerDevice"`
}

// UpdateQps 更新分组 QPS
func (h *GroupHandler) UpdateQps(c *gin.Context) {
	var req UpdateGroupQpsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	updates := make(map[string]interface{})
	if req.QuotaQpsGroup > 0 {
		updates["quota_qps_group"] = req.QuotaQpsGroup
	}
	if req.QuotaQpsPerDevice > 0 {
		updates["quota_qps_per_device"] = req.QuotaQpsPerDevice
	}

	if err := database.GetDB().Model(&model.GroupConfig{}).
		Where("group_name = ?", req.GroupName).
		Updates(updates).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

// GetGroupDevices 获取分组设备列表
type DeviceInfoVO struct {
	GroupName      string `json:"groupName"`
	DeviceID       string `json:"deviceId"`
	DeviceIP       string `json:"deviceIp"`
	RegisterTime   string `json:"registerTime"`
	LastActiveTime string `json:"lastActiveTime"`
	Status         string `json:"status"`
}

func (h *GroupHandler) GetDevices(c *gin.Context) {
	groupName := c.Param("groupName")

	var devices []model.GroupDevice
	if err := database.GetDB().Where("group_name = ?", groupName).Find(&devices).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	var vos []DeviceInfoVO
	now := time.Now()
	for _, d := range devices {
		status := "offline"
		if now.Sub(d.LastActiveTime) < 5*time.Minute {
			status = "online"
		}
		vos = append(vos, DeviceInfoVO{
			GroupName:      d.GroupName,
			DeviceID:       d.DeviceID,
			DeviceIP:       d.RemoteIP,
			RegisterTime:   d.CreateDate.Format("2006-01-02 15:04:05"),
			LastActiveTime: d.LastActiveTime.Format("2006-01-02 15:04:05"),
			Status:         status,
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
	})
}

// DeleteDeviceRequest 删除设备请求
type DeleteDeviceRequest struct {
	GroupName string `json:"groupName" binding:"required"`
	DeviceID  string `json:"deviceId" binding:"required"`
}

// DeleteDevice 删除设备
func (h *GroupHandler) DeleteDevice(c *gin.Context) {
	var req DeleteDeviceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	if err := database.GetDB().Where("group_name = ? AND device_id = ?", req.GroupName, req.DeviceID).
		Delete(&model.GroupDevice{}).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

// GetGroupActions 获取分组 Action 列表
func (h *GroupHandler) GetActions(c *gin.Context) {
	groupName := c.Param("groupName")

	var actions []model.GroupAction
	if err := database.GetDB().Where("group_name = ?", groupName).Find(&actions).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    actions,
	})
}

// AddActionRequest 添加 Action 请求
type AddActionRequest struct {
	GroupName  string `json:"groupName" binding:"required"`
	ActionName string `json:"actionName" binding:"required"`
}

// AddAction 添加 Action
func (h *GroupHandler) AddAction(c *gin.Context) {
	var req AddActionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 检查分组是否存在
	var group model.GroupConfig
	if err := database.GetDB().Where("group_name = ?", req.GroupName).First(&group).Error; err != nil {
		c.JSON(404, gin.H{"code": 404, "message": "group not found"})
		return
	}

	// 检查 action 是否已存在
	var existing model.GroupAction
	if err := database.GetDB().Where("group_name = ? AND action_name = ?", req.GroupName, req.ActionName).First(&existing).Error; err == nil {
		c.JSON(409, gin.H{"code": 409, "message": "action already exists"})
		return
	}

	action := model.GroupAction{
		GroupName:  req.GroupName,
		ActionName: req.ActionName,
		CreateDate: time.Now(),
	}

	if err := database.GetDB().Create(&action).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    action.ID,
	})
}

// DeleteActionRequest 删除 Action 请求
type DeleteActionRequest struct {
	GroupName  string `json:"groupName" binding:"required"`
	ActionName string `json:"actionName" binding:"required"`
}

// DeleteAction 删除 Action
func (h *GroupHandler) DeleteAction(c *gin.Context) {
	var req DeleteActionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	if err := database.GetDB().Where("group_name = ? AND action_name = ?", req.GroupName, req.ActionName).
		Delete(&model.GroupAction{}).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

// DisableDeviceRequest 禁用/启用设备请求
type DisableDeviceRequest struct {
	GroupName string `json:"groupName" binding:"required"`
	DeviceID  string `json:"deviceId" binding:"required"`
	Disable   bool   `json:"disable"` // true=禁用，false=启用
}

// DisableDevice 禁用/启用设备
func (h *GroupHandler) DisableDevice(c *gin.Context) {
	var req DisableDeviceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 检查设备是否存在
	var device model.GroupDevice
	if err := database.GetDB().Where("group_name = ? AND device_id = ?", req.GroupName, req.DeviceID).First(&device).Error; err != nil {
		c.JSON(404, gin.H{"code": 404, "message": "device not found"})
		return
	}

	if req.Disable {
		// 禁用设备：将最后活跃时间设置为过去
		if err := database.GetDB().Model(&device).Update("last_active_time", time.Now().Add(-24*time.Hour)).Error; err != nil {
			c.JSON(500, gin.H{"code": 500, "message": err.Error()})
			return
		}
	} else {
		// 启用设备：更新最后活跃时间为当前
		if err := database.GetDB().Model(&device).Update("last_active_time", time.Now()).Error; err != nil {
			c.JSON(500, gin.H{"code": 500, "message": err.Error()})
			return
		}
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}
