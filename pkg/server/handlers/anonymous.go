package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
	pkgconfig "github.com/mrh30000/go-rpc/pkg/server/config"
	"github.com/mrh30000/go-rpc/pkg/server/middleware"
)

// AnonymousGroupHandler 匿名分组处理器
type AnonymousGroupHandler struct {
	groupRepo repository.GroupRepository
}

// NewAnonymousGroupHandler 创建匿名分组处理器
func NewAnonymousGroupHandler(groupRepo repository.GroupRepository) *AnonymousGroupHandler {
	return &AnonymousGroupHandler{groupRepo: groupRepo}
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

	var devices []struct {
		GroupName      string    `json:"group_name"`
		LastActiveTime time.Time `json:"last_active_time"`
	}

	if err := db.Table("group_device gd").
		Where("NOT EXISTS (SELECT 1 FROM group_config gc WHERE gc.group_name = gd.group_name)").
		Find(&devices).Error; err != nil {
		InternalError(c, err.Error())
		return
	}

	if len(devices) == 0 {
		Success(c, []AnonymousGroupVO{})
		return
	}

	groupMap := make(map[string][]time.Time)
	for _, d := range devices {
		groupMap[d.GroupName] = append(groupMap[d.GroupName], d.LastActiveTime)
	}

	activeThreshold := time.Now().Add(-ClientInactiveThreshold)

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

	Success(c, vos)
}

// ListOptimized 优化版本：使用数据库聚合查询
func (h *AnonymousGroupHandler) ListOptimized(c *gin.Context) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return
	}
	if !user.IsAdmin {
		Forbidden(c, "需要管理员权限")
		return
	}

	activeThreshold := time.Now().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	stats, err := h.groupRepo.FindAnonymousDeviceGroups(activeThreshold)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	if len(stats) == 0 {
		Success(c, []AnonymousGroupVO{})
		return
	}

	vos := make([]AnonymousGroupVO, len(stats))
	for i, s := range stats {
		vos[i] = AnonymousGroupVO{
			GroupName:        s.GroupName,
			AvailableClients: s.AvailableClients,
			DisabledClients:  s.DisabledClients,
			TotalClients:     s.TotalClients,
		}
	}

	Success(c, vos)
}

// DeleteAnonymousGroupRequest 删除匿名分组请求
type DeleteAnonymousGroupRequest struct {
	GroupName string `json:"groupName" binding:"required"`
}

// Delete 删除匿名分组
func (h *AnonymousGroupHandler) Delete(c *gin.Context) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return
	}
	if !user.IsAdmin {
		Forbidden(c, "需要管理员权限")
		return
	}

	var req DeleteAnonymousGroupRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	isAnon, err := h.groupRepo.IsAnonymousGroup(req.GroupName)
	if err != nil {
		InternalError(c, err.Error())
		return
	}
	if !isAnon {
		BadRequest(c, "不能删除已注册的分组，请在分组管理中删除")
		return
	}

	count, err := h.groupRepo.DeleteAnonymousGroupDevices(req.GroupName)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, count)
}

// ConvertAnonymousGroupRequest 转换匿名分组请求
type ConvertAnonymousGroupRequest struct {
	GroupName         string  `json:"groupName" binding:"required"`
	QuotaQpsGroup     float64 `json:"quotaQpsGroup"`
	QuotaQpsPerDevice float64 `json:"quotaQpsPerDevice"`
}

// ConvertAnonymousGroup 将匿名分组转换为正式分组
func (h *AnonymousGroupHandler) ConvertAnonymousGroup(c *gin.Context) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return
	}
	if !user.IsAdmin {
		Forbidden(c, "需要管理员权限")
		return
	}

	var req ConvertAnonymousGroupRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	isAnon, err := h.groupRepo.IsAnonymousGroup(req.GroupName)
	if err != nil {
		InternalError(c, err.Error())
		return
	}
	if !isAnon {
		BadRequest(c, "该分组已是正式分组，无需转换")
		return
	}

	var defaultGroupQps float64 = 100
	var defaultDeviceQps float64 = 10
	cfgSvc, cfgExists := c.Get("configService")
	if cfgExists {
		if configSvc, ok := cfgSvc.(pkgconfig.Service); ok {
			defaultGroupQps = configSvc.GetConfigFloat(pkgconfig.ConfigKeyDefaultQuotaGroup, 100.0)
			defaultDeviceQps = configSvc.GetConfigFloat(pkgconfig.ConfigKeyDefaultQuotaPerDevice, 10.0)
		}
	}

	// Use direct DB for transaction
	db := database.GetDB()
	tx := db.Begin()

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

	if err := tx.Create(&group).Error; err != nil {
		tx.Rollback()
		InternalError(c, err.Error())
		return
	}

	txRepo := h.groupRepo.WithTx(tx)
	for _, actionName := range DefaultGroupActions {
		existingAction, err := txRepo.FindAction(req.GroupName, actionName)
		if err != nil {
			logger.Warnf("Failed to check action existence: group=%s, action=%s, err=%v", req.GroupName, actionName, err)
			continue
		}
		if existingAction == nil {
			action := model.GroupAction{
				GroupName:  req.GroupName,
				ActionName: actionName,
				CreateDate: time.Now(),
			}
			if err := txRepo.CreateAction(&action); err != nil {
				logger.Warnf("Failed to create default action: group=%s, action=%s, err=%v", req.GroupName, actionName, err)
			} else {
				logger.Infof("Default action created during conversion: group=%s, action=%s", req.GroupName, actionName)
			}
		}
	}

	tx.Commit()

	middleware.InvalidateGroup(req.GroupName)

	auditConvertGroup(c, "anonymous:"+req.GroupName, req.GroupName)
	Success(c, group.ID)
}
