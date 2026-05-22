package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/config"
	"github.com/mrh30000/go-rpc/pkg/server/middleware"
)

// GroupHandler 分组管理处理器
type GroupHandler struct {
	groupRepo repository.GroupRepository
}

// NewGroupHandler 创建分组处理器
func NewGroupHandler(groupRepo repository.GroupRepository) *GroupHandler {
	return &GroupHandler{groupRepo: groupRepo}
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
	user, exists := middleware.GetCurrentUser(c)
	if !exists || user == nil {
		Unauthorized(c, "请先登录")
		return
	}

	activeThreshold := time.Now().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	stats, err := h.groupRepo.GetGroupStats(user.UserName, user.IsAdmin, activeThreshold)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	vos := make([]GroupInfoVO, 0, len(stats))
	for _, s := range stats {
		vos = append(vos, GroupInfoVO{
			ID:                s.ID,
			GroupName:         s.GroupName,
			UserName:          s.UserName,
			QuotaQpsGroup:     s.QuotaQpsGroup,
			QuotaQpsPerDevice: s.QuotaQpsPerDevice,
			CreateTime:        s.CreateDate,
			AvailableClients:  s.AvailableClients,
			DisabledClients:   s.DisabledClients,
			AvailableClientSize: s.AvailableClients,
			DisableClientSize:   s.DisabledClients,
		})
	}

	SuccessWithTotal(c, vos, int64(len(vos)))
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
		BadRequest(c, err.Error())
		return
	}

	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		Unauthorized(c, "请先登录")
		return
	}

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

	if group.QuotaQpsGroup <= 0 {
		group.QuotaQpsGroup = defaultGroupQps
	}
	if group.QuotaQpsPerDevice <= 0 {
		group.QuotaQpsPerDevice = defaultDeviceQps
	}

	if err := h.groupRepo.CreateGroup(&group); err != nil {
		InternalError(c, err.Error())
		return
	}

	middleware.InvalidateGroup(group.GroupName)

	Success(c, group.ID)
}

// DeleteGroupRequest 删除分组请求
type DeleteGroupRequest struct {
	GroupName string `json:"groupName" binding:"required"`
}

// Delete 删除分组
func (h *GroupHandler) Delete(c *gin.Context) {
	var req DeleteGroupRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}
	if _, ok := authorizeGroupAccess(c, req.GroupName, h.groupRepo); !ok {
		return
	}

	// Use direct DB for transaction
	db := database.GetDB()
	tx := db.Begin()

	txRepo := h.groupRepo.WithTx(tx)
	if err := txRepo.DeleteDevicesByGroup(req.GroupName); err != nil {
		tx.Rollback()
		InternalError(c, err.Error())
		return
	}
	if err := txRepo.DeleteActionsByGroup(req.GroupName); err != nil {
		tx.Rollback()
		InternalError(c, err.Error())
		return
	}
	if err := txRepo.DeleteGroup(req.GroupName); err != nil {
		tx.Rollback()
		InternalError(c, err.Error())
		return
	}

	tx.Commit()

	middleware.InvalidateGroup(req.GroupName)

	auditDeleteGroup(c, req.GroupName)
	Success(c, nil)
}

// GetGroupDetail 获取分组详情
func (h *GroupHandler) GetDetail(c *gin.Context) {
	groupName := c.Param("groupName")

	group, ok := authorizeGroupAccess(c, groupName, h.groupRepo)
	if !ok {
		return
	}

	activeThreshold := time.Now().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	available, disabled, err := h.groupRepo.GetGroupDeviceStats(groupName, activeThreshold)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, gin.H{
			"groupName":         group.GroupName,
			"userName":          group.UserName,
			"createTime":        group.CreateDate.Format("2006-01-02 15:04:05"),
			"quotaQpsGroup":     group.QuotaQpsGroup,
			"quotaQpsPerDevice": group.QuotaQpsPerDevice,
			"availableClients":  available,
			"disabledClients":   disabled,
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
		BadRequest(c, err.Error())
		return
	}
	if _, ok := authorizeGroupAccess(c, req.GroupName, h.groupRepo); !ok {
		return
	}

	updates := make(map[string]interface{})
	if req.QuotaQpsGroup > 0 {
		updates["quota_qps_group"] = req.QuotaQpsGroup
	}
	if req.QuotaQpsPerDevice > 0 {
		updates["quota_qps_per_device"] = req.QuotaQpsPerDevice
	}

	if err := h.groupRepo.UpdateGroup(req.GroupName, updates); err != nil {
		InternalError(c, err.Error())
		return
	}

	middleware.InvalidateGroup(req.GroupName)

	auditUpdateQps(c, "group", req.GroupName, req.QuotaQpsGroup)
	Success(c, nil)
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
	if _, ok := authorizeGroupAccess(c, groupName, h.groupRepo); !ok {
		return
	}

	devices, err := h.groupRepo.FindDevicesByGroup(groupName)
	if err != nil {
		InternalError(c, err.Error())
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

	Success(c, vos)
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
		BadRequest(c, err.Error())
		return
	}
	if _, ok := authorizeGroupAccess(c, req.GroupName, h.groupRepo); !ok {
		return
	}

	if err := h.groupRepo.DeleteDevice(req.GroupName, req.DeviceID); err != nil {
		InternalError(c, err.Error())
		return
	}

	auditDeleteDevice(c, req.GroupName, req.DeviceID)
	Success(c, nil)
}

// GetGroupActions 获取分组 Action 列表
func (h *GroupHandler) GetActions(c *gin.Context) {
	groupName := c.Param("groupName")
	if _, ok := authorizeGroupAccess(c, groupName, h.groupRepo); !ok {
		return
	}

	actions, err := h.groupRepo.FindActionsByGroup(groupName)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, actions)
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
		BadRequest(c, err.Error())
		return
	}
	if _, ok := authorizeGroupAccess(c, req.GroupName, h.groupRepo); !ok {
		return
	}

	group, err := h.groupRepo.FindGroupByName(req.GroupName)
	if err != nil {
		InternalError(c, err.Error())
		return
	}
	if group == nil {
		NotFound(c, "group not found")
		return
	}

	existing, err := h.groupRepo.FindAction(req.GroupName, req.ActionName)
	if err != nil {
		InternalError(c, err.Error())
		return
	}
	if existing != nil {
		Error(c, 409, "action already exists")
		return
	}

	action := model.GroupAction{
		GroupName:  req.GroupName,
		ActionName: req.ActionName,
		CreateDate: time.Now(),
	}

	if err := h.groupRepo.CreateAction(&action); err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, action.ID)
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
		BadRequest(c, err.Error())
		return
	}
	if _, ok := authorizeGroupAccess(c, req.GroupName, h.groupRepo); !ok {
		return
	}

	if err := h.groupRepo.DeleteAction(req.GroupName, req.ActionName); err != nil {
		InternalError(c, err.Error())
		return
	}

	auditDeleteAction(c, req.GroupName, req.ActionName)
	Success(c, nil)
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
		BadRequest(c, err.Error())
		return
	}
	if _, ok := authorizeGroupAccess(c, req.GroupName, h.groupRepo); !ok {
		return
	}

	device, err := h.groupRepo.FindDevice(req.GroupName, req.DeviceID)
	if err != nil {
		InternalError(c, err.Error())
		return
	}
	if device == nil {
		NotFound(c, "device not found")
		return
	}

	if req.Disable {
		if err := h.groupRepo.UpdateDevice(req.GroupName, req.DeviceID, map[string]interface{}{
			"last_active_time": time.Now().Add(-24 * time.Hour),
		}); err != nil {
			InternalError(c, err.Error())
			return
		}
	} else {
		if err := h.groupRepo.UpdateDevice(req.GroupName, req.DeviceID, map[string]interface{}{
			"last_active_time": time.Now(),
		}); err != nil {
			InternalError(c, err.Error())
			return
		}
	}

	auditDisableDevice(c, req.GroupName, req.DeviceID)
	Success(c, nil)
}
