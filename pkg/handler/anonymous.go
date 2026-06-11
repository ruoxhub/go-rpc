package handler

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/client"
	pkgconfig "github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// AnonymousGroupHandler 匿名分组处理器
type AnonymousGroupHandler struct {
	groupRepo     repository.GroupRepository
	clientManager anonymousClientManager
}

type anonymousClientManager interface {
	GetAllGroups() []string
	GetClientsByGroup(group string) []*client.RpcClient
	Unregister(groupName, clientID string)
}

// NewAnonymousGroupHandler 创建匿名分组处理器
func NewAnonymousGroupHandler(groupRepo repository.GroupRepository, clientManager anonymousClientManager) *AnonymousGroupHandler {
	return &AnonymousGroupHandler{groupRepo: groupRepo, clientManager: clientManager}
}

// AnonymousGroupVO 匿名分组 VO
type AnonymousGroupVO struct {
	GroupName        string `json:"groupName"`
	AvailableClients int64  `json:"availableClients"`
	DisabledClients  int64  `json:"disabledClients"`
	TotalClients     int64  `json:"totalClients"`
}

// List 获取匿名分组列表
// 匿名分组定义：当前内存连接中未归属正式分组的设备
func (h *AnonymousGroupHandler) List(c *gin.Context) {
	Success(c, buildAnonymousGroupVOs(h.clientManager))
}

// ListOptimized 使用内存中的实时连接状态统计匿名分组。
func (h *AnonymousGroupHandler) ListOptimized(c *gin.Context) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return
	}
	if !user.IsAdmin {
		Forbidden(c, "需要管理员权限")
		return
	}

	Success(c, buildAnonymousGroupVOs(h.clientManager))
}

func buildAnonymousGroupVOs(clientManager anonymousClientManager) []AnonymousGroupVO {
	if clientManager == nil {
		return []AnonymousGroupVO{}
	}

	activeThreshold := time.Now().Add(-ClientInactiveThreshold)
	groups := clientManager.GetAllGroups()
	vos := make([]AnonymousGroupVO, 0, len(groups))

	for _, groupName := range groups {
		clients := clientManager.GetClientsByGroup(groupName)
		if len(clients) == 0 {
			continue
		}

		var availableCount, disabledCount int64
		registeredGroup := false
		for _, c := range clients {
			if c == nil {
				continue
			}
			if c.IsRegisteredGroup() {
				registeredGroup = true
				break
			}
			if c.GetStatus() == client.StatusOnline && c.GetLastActive().After(activeThreshold) {
				availableCount++
				continue
			}
			disabledCount++
		}

		if registeredGroup {
			continue
		}

		totalCount := availableCount + disabledCount
		if totalCount == 0 {
			continue
		}

		vos = append(vos, AnonymousGroupVO{
			GroupName:        groupName,
			AvailableClients: availableCount,
			DisabledClients:  disabledCount,
			TotalClients:     totalCount,
		})
	}

	return vos
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

	if h.clientManager == nil {
		InternalError(c, "client manager unavailable")
		return
	}

	clients := h.clientManager.GetClientsByGroup(req.GroupName)
	for _, rpcClient := range clients {
		if rpcClient != nil && rpcClient.IsRegisteredGroup() {
			BadRequest(c, "不能删除已注册的分组，请在分组管理中删除")
			return
		}
	}
	if len(clients) == 0 {
		Success(c, int64(0))
		return
	}

	var count int64
	for _, rpcClient := range clients {
		if rpcClient == nil {
			continue
		}
		h.clientManager.Unregister(req.GroupName, rpcClient.ClientID)
		count++
	}

	Success(c, count)
}

func (h *AnonymousGroupHandler) markGroupRegistered(groupName string) {
	if h.clientManager == nil {
		return
	}

	clients := h.clientManager.GetClientsByGroup(groupName)
	for _, c := range clients {
		if c != nil {
			c.SetRegisteredGroup(true)
		}
	}
}

func (h *AnonymousGroupHandler) isAnonymousGroupInMemory(groupName string) bool {
	if h.clientManager == nil {
		return false
	}

	clients := h.clientManager.GetClientsByGroup(groupName)
	if len(clients) == 0 {
		return false
	}
	for _, c := range clients {
		if c != nil && c.IsRegisteredGroup() {
			return false
		}
	}
	return true
}

func (h *AnonymousGroupHandler) validateAnonymousGroupForConvert(c *gin.Context, groupName string) bool {
	if h.isAnonymousGroupInMemory(groupName) {
		return true
	}

	if h.groupRepo == nil {
		BadRequest(c, "该分组已是正式分组，无需转换")
		return false
	}

	isAnon, err := h.groupRepo.IsAnonymousGroup(groupName)
	if err != nil {
		InternalError(c, err.Error())
		return false
	}
	if !isAnon {
		BadRequest(c, "该分组已是正式分组，无需转换")
		return false
	}
	return true
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

	if !h.validateAnonymousGroupForConvert(c, req.GroupName) {
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

	// Begin transaction
	txRepo := h.groupRepo.BeginTx()
	committed := false
	defer func() {
		if !committed {
			txRepo.Rollback()
		}
	}()

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

	if err := txRepo.CreateGroup(&group); err != nil {
		InternalError(c, err.Error())
		return
	}

	if h.clientManager != nil {
		for _, rpcClient := range h.clientManager.GetClientsByGroup(req.GroupName) {
			if rpcClient == nil {
				continue
			}
			device := model.GroupDevice{
				GroupName:      req.GroupName,
				DeviceID:       rpcClient.ClientID,
				LastActiveTime: rpcClient.GetLastActive(),
			}
			if err := txRepo.UpsertDevice(&device); err != nil {
				InternalError(c, err.Error())
				return
			}
		}
	}

	for _, actionName := range model.DefaultGroupActions {
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

	if err := txRepo.Commit(); err != nil {
		InternalError(c, "commit failed: "+err.Error())
		return
	}
	committed = true

	middleware.InvalidateGroup(req.GroupName)
	h.markGroupRegistered(req.GroupName)

	auditConvertGroup(c, "anonymous:"+req.GroupName, req.GroupName)
	Success(c, group.ID)
}
