package handlers

import (
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"time"

	"github.com/gin-gonic/gin"
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
}

// List 获取分组列表
func (h *GroupHandler) List(c *gin.Context) {
	var groups []model.GroupConfig
	result := database.GetDB().Find(&groups)

	var vos []GroupInfoVO
	for _, g := range groups {
		// 统计在线和禁用设备数量
		var availableCount, disabledCount int64
		database.GetDB().Model(&model.GroupDevice{}).
			Where("group_name = ? AND last_active_time > ?", g.GroupName, time.Now().Add(-5*time.Minute)).
			Count(&availableCount)
		database.GetDB().Model(&model.GroupDevice{}).
			Where("group_name = ? AND last_active_time <= ?", g.GroupName, time.Now().Add(-5*time.Minute)).
			Count(&disabledCount)

		vos = append(vos, GroupInfoVO{
			ID:                g.ID,
			GroupName:         g.GroupName,
			UserName:          g.UserName,
			QuotaQpsGroup:     g.QuotaQpsGroup,
			QuotaQpsPerDevice: g.QuotaQpsPerDevice,
			CreateTime:        g.CreateDate.Format("2006-01-02 15:04:05"),
			AvailableClients:  availableCount,
			DisabledClients:   disabledCount,
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
		"total":   result.RowsAffected,
	})
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

	// TODO: 从上下文中获取当前用户名
	group := model.GroupConfig{
		GroupName:         req.GroupName,
		UserName:          "current_user", // 临时写死
		QuotaQpsGroup:     req.QuotaQpsGroup,
		QuotaQpsPerDevice: req.QuotaQpsPerDevice,
		CreateDate:        time.Now(),
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

	// 统计在线和禁用设备数量
	var availableCount, disabledCount int64
	database.GetDB().Model(&model.GroupDevice{}).
		Where("group_name = ? AND last_active_time > ?", groupName, time.Now().Add(-5*time.Minute)).
		Count(&availableCount)
	database.GetDB().Model(&model.GroupDevice{}).
		Where("group_name = ? AND last_active_time <= ?", groupName, time.Now().Add(-5*time.Minute)).
		Count(&disabledCount)

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data": gin.H{
			"groupName":         group.GroupName,
			"userName":          group.UserName,
			"createTime":        group.CreateDate.Format("2006-01-02 15:04:05"),
			"quotaQpsGroup":     group.QuotaQpsGroup,
			"quotaQpsPerDevice": group.QuotaQpsPerDevice,
			"availableClients":  availableCount,
			"disabledClients":   disabledCount,
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
