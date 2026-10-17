package handler

import (
	"fmt"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// GroupHandler 分组管理处理器
type GroupHandler struct {
	groupRepo     repository.GroupRepository
	authMW        *middleware.AuthMiddleware
	clientManager *client.ClientManager
}

// NewGroupHandler 创建分组处理器
func NewGroupHandler(groupRepo repository.GroupRepository, authMW *middleware.AuthMiddleware, clientManager *client.ClientManager) *GroupHandler {
	return &GroupHandler{
		groupRepo:     groupRepo,
		authMW:        authMW,
		clientManager: clientManager,
	}
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

	activeThreshold := time.Now().UTC().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	stats, err := h.groupRepo.GetGroupStats(user.UserName, user.IsAdmin, activeThreshold)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	vos := make([]GroupInfoVO, 0, len(stats))
	for _, s := range stats {
		availableClients := s.AvailableClients
		if h.clientManager != nil {
			activeCutoff := time.Now().Add(-ClientInactiveThreshold)
			var memOnline int64
			for _, cl := range h.clientManager.GetClientsByGroup(s.GroupName) {
				if cl != nil && cl.GetStatus() == client.StatusOnline && cl.GetLastActive().After(activeCutoff) {
					memOnline++
				}
			}
			availableClients = memOnline
		}

		vos = append(vos, GroupInfoVO{
			ID:                  s.ID,
			GroupName:           s.GroupName,
			UserName:            s.UserName,
			QuotaQpsGroup:       s.QuotaQpsGroup,
			QuotaQpsPerDevice:   s.QuotaQpsPerDevice,
			CreateTime:          s.CreateDate,
			AvailableClients:    availableClients,
			DisabledClients:     s.DisabledClients,
			AvailableClientSize: availableClients,
			DisableClientSize:   s.DisabledClients,
		})
	}

	OKWithTotal(c, vos, int64(len(vos)))
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

	h.authMW.InvalidateGroup(group.GroupName)

	OK(c, group.ID)
}

// DeleteGroupRequest 删除分组请求
type DeleteGroupRequest struct {
	GroupName string `json:"groupName" binding:"required"`
}

// deleteGroupCascade 在独立事务中删除分组的设备、Action 与分组记录。
func deleteGroupCascade(repo repository.GroupRepository, groupName string) error {
	txRepo := repo.BeginTx()
	committed := false
	defer func() {
		if !committed {
			txRepo.Rollback()
		}
	}()

	steps := []struct {
		name string
		fn   func() error
	}{
		{"delete devices", func() error { return txRepo.DeleteDevicesByGroup(groupName) }},
		{"delete actions", func() error { return txRepo.DeleteActionsByGroup(groupName) }},
		{"delete group", func() error { return txRepo.DeleteGroup(groupName) }},
	}
	for _, step := range steps {
		if err := step.fn(); err != nil {
			return fmt.Errorf("%s: %w", step.name, err)
		}
	}

	if err := txRepo.Commit(); err != nil {
		return fmt.Errorf("commit failed: %w", err)
	}
	committed = true
	return nil
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

	if err := deleteGroupCascade(h.groupRepo, req.GroupName); err != nil {
		InternalError(c, err.Error())
		return
	}

	h.authMW.InvalidateGroup(req.GroupName)

	auditDeleteGroup(c, req.GroupName)
	OK(c, nil)
}

// maxBatchGroups 单次批量操作的分组上限，避免一次请求打爆数据库。
const maxBatchGroups = 100

// BatchGroupFailure 批量操作中单个分组的失败明细。
type BatchGroupFailure struct {
	GroupName string `json:"groupName"`
	Reason    string `json:"reason"`
}

// BatchGroupResult 批量操作的逐条结果。
type BatchGroupResult struct {
	Succeeded []string            `json:"succeeded"`
	Failed    []BatchGroupFailure `json:"failed"`
}

// normalizeBatchGroupNames 去重并剔除空串，保留首次出现的顺序。
func normalizeBatchGroupNames(names []string) []string {
	seen := make(map[string]struct{}, len(names))
	result := make([]string, 0, len(names))
	for _, name := range names {
		if name == "" {
			continue
		}
		if _, ok := seen[name]; ok {
			continue
		}
		seen[name] = struct{}{}
		result = append(result, name)
	}
	return result
}

// bindBatchGroupNames 解析并校验批量分组名列表，失败时已写出响应。
func bindBatchGroupNames(c *gin.Context, raw []string) ([]string, bool) {
	if _, ok := getAuthenticatedUser(c); !ok {
		return nil, false
	}
	names := normalizeBatchGroupNames(raw)
	if len(names) == 0 {
		BadRequest(c, "groupNames 不能为空")
		return nil, false
	}
	if len(names) > maxBatchGroups {
		BadRequest(c, fmt.Sprintf("单次批量操作最多 %d 个分组", maxBatchGroups))
		return nil, false
	}
	return names, true
}

// BatchDeleteGroupsRequest 批量删除分组请求
type BatchDeleteGroupsRequest struct {
	GroupNames []string `json:"groupNames" binding:"required,min=1"`
}

// BatchDelete 批量删除分组。逐条独立事务，部分失败不影响其余分组。
func (h *GroupHandler) BatchDelete(c *gin.Context) {
	var req BatchDeleteGroupsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}
	names, ok := bindBatchGroupNames(c, req.GroupNames)
	if !ok {
		return
	}

	result := BatchGroupResult{Succeeded: []string{}, Failed: []BatchGroupFailure{}}
	for _, name := range names {
		if _, accessErr := checkGroupAccess(c, name, h.groupRepo); accessErr != nil {
			result.Failed = append(result.Failed, BatchGroupFailure{GroupName: name, Reason: accessErr.message})
			continue
		}

		if err := deleteGroupCascade(h.groupRepo, name); err != nil {
			result.Failed = append(result.Failed, BatchGroupFailure{GroupName: name, Reason: err.Error()})
			continue
		}

		h.authMW.InvalidateGroup(name)
		auditDeleteGroup(c, name)
		result.Succeeded = append(result.Succeeded, name)
	}

	OK(c, result)
}

// GetGroupDetail 获取分组详情
func (h *GroupHandler) GetDetail(c *gin.Context) {
	groupName := c.Param("groupName")

	group, ok := authorizeGroupAccess(c, groupName, h.groupRepo)
	if !ok {
		return
	}

	activeThreshold := time.Now().UTC().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	available, disabled, err := h.groupRepo.GetGroupDeviceStats(groupName, activeThreshold)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

	if h.clientManager != nil {
		activeCutoff := time.Now().Add(-ClientInactiveThreshold)
		var memOnline int64
		for _, cl := range h.clientManager.GetClientsByGroup(groupName) {
			if cl != nil && cl.GetStatus() == client.StatusOnline && cl.GetLastActive().After(activeCutoff) {
				memOnline++
			}
		}
		available = memOnline
	}

	OK(c, gin.H{
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

	h.authMW.InvalidateGroup(req.GroupName)

	auditUpdateQps(c, "group", req.GroupName, req.QuotaQpsGroup)
	OK(c, nil)
}

// BatchUpdateQpsRequest 批量更新分组 QPS 请求
type BatchUpdateQpsRequest struct {
	GroupNames        []string `json:"groupNames" binding:"required,min=1"`
	QuotaQpsGroup     float64  `json:"quotaQpsGroup"`
	QuotaQpsPerDevice float64  `json:"quotaQpsPerDevice"`
}

// BatchUpdateQps 批量更新分组 QPS 限制。逐条处理，部分失败不影响其余分组。
func (h *GroupHandler) BatchUpdateQps(c *gin.Context) {
	var req BatchUpdateQpsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	updates := make(map[string]interface{})
	if req.QuotaQpsGroup > 0 {
		updates["quota_qps_group"] = req.QuotaQpsGroup
	}
	if req.QuotaQpsPerDevice > 0 {
		updates["quota_qps_per_device"] = req.QuotaQpsPerDevice
	}
	if len(updates) == 0 {
		BadRequest(c, "quotaQpsGroup 与 quotaQpsPerDevice 至少提供一个大于 0 的值")
		return
	}

	names, ok := bindBatchGroupNames(c, req.GroupNames)
	if !ok {
		return
	}

	result := BatchGroupResult{Succeeded: []string{}, Failed: []BatchGroupFailure{}}
	for _, name := range names {
		if _, accessErr := checkGroupAccess(c, name, h.groupRepo); accessErr != nil {
			result.Failed = append(result.Failed, BatchGroupFailure{GroupName: name, Reason: accessErr.message})
			continue
		}

		if err := h.groupRepo.UpdateGroup(name, updates); err != nil {
			result.Failed = append(result.Failed, BatchGroupFailure{GroupName: name, Reason: err.Error()})
			continue
		}

		h.authMW.InvalidateGroup(name)
		auditUpdateQps(c, "group", name, req.QuotaQpsGroup)
		result.Succeeded = append(result.Succeeded, name)
	}

	OK(c, result)
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

	// 离线直接丢弃，只返回当前实时在线客户端
	var vos []DeviceInfoVO
	if h.clientManager != nil {
		activeThreshold := time.Now().Add(-ClientInactiveThreshold)
		clients := h.clientManager.GetClientsByGroup(groupName)
		for _, cl := range clients {
			if cl == nil {
				continue
			}
			lastActive := cl.GetLastActive()
			if cl.GetStatus() == client.StatusOnline && lastActive.After(activeThreshold) {
				vos = append(vos, DeviceInfoVO{
					GroupName:      groupName,
					DeviceID:       cl.ClientID,
					DeviceIP:       "",
					RegisterTime:   lastActive.Format("2006-01-02 15:04:05"),
					LastActiveTime: lastActive.Format("2006-01-02 15:04:05"),
					Status:         "online",
				})
			}
		}
	} else if h.groupRepo != nil {
		// 单测或无 clientManager 时的兜底
		devices, err := h.groupRepo.FindDevicesByGroup(groupName)
		if err != nil {
			InternalError(c, err.Error())
			return
		}
		now := time.Now()
		for _, d := range devices {
			if now.Sub(d.LastActiveTime) < ClientInactiveThreshold {
				vos = append(vos, DeviceInfoVO{
					GroupName:      d.GroupName,
					DeviceID:       d.DeviceID,
					DeviceIP:       d.RemoteIP,
					RegisterTime:   d.CreateDate.Format("2006-01-02 15:04:05"),
					LastActiveTime: d.LastActiveTime.Format("2006-01-02 15:04:05"),
					Status:         "online",
				})
			}
		}
	}

	OK(c, vos)
}

// DeleteDeviceRequest 删除设备请求
type DeleteDeviceRequest struct {
	GroupName string `json:"groupName" binding:"required"`
	DeviceID  string `json:"deviceId" binding:"required"`
}

// DeleteDevice 删除/下线设备
func (h *GroupHandler) DeleteDevice(c *gin.Context) {
	var req DeleteDeviceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}
	if _, ok := authorizeGroupAccess(c, req.GroupName, h.groupRepo); !ok {
		return
	}

	if h.clientManager != nil {
		h.clientManager.Unregister(req.GroupName, req.DeviceID)
	}
	if h.groupRepo != nil {
		if err := h.groupRepo.DeleteDevice(req.GroupName, req.DeviceID); err != nil {
			InternalError(c, err.Error())
			return
		}
	}

	auditDeleteDevice(c, req.GroupName, req.DeviceID)
	OK(c, nil)
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

	OK(c, actions)
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

	existing, err := h.groupRepo.FindAction(req.GroupName, req.ActionName)
	if err != nil {
		InternalError(c, err.Error())
		return
	}
	if existing != nil {
		BadRequest(c, "action already exists")
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

	OK(c, action.ID)
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
	OK(c, nil)
}

// registerGroupRoutes 注册分组管理路由。抽成独立函数便于对路由冲突做回归测试。
func registerGroupRoutes(groups *gin.RouterGroup, h *GroupHandler) {
	groups.GET("", h.List)
	groups.POST("", h.Create)
	groups.DELETE("", h.Delete)
	groups.GET("/:groupName", h.GetDetail)
	groups.PUT("/qps", h.UpdateQps)
	groups.GET("/:groupName/devices", h.GetDevices)
	groups.DELETE("/devices", h.DeleteDevice)
	groups.GET("/:groupName/actions", h.GetActions)
	groups.POST("/actions", h.AddAction)
	groups.DELETE("/actions", h.DeleteAction)
	groups.POST("/batch/delete", h.BatchDelete)
	groups.PUT("/batch/qps", h.BatchUpdateQps)
}
