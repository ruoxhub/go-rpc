package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
	pkgconfig "github.com/mrh30000/go-rpc/pkg/server/config"
	"github.com/mrh30000/go-rpc/pkg/server/middleware"
	"github.com/mrh30000/go-rpc/pkg/utils/password"
)

// LoginRequest 登录请求
type LoginRequest struct {
	UserName string `form:"userName" binding:"required"`
	Password string `form:"password" binding:"required"`
}

// HandleLogin 处理登录请求
func HandleLogin(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBind(&req); err != nil {
		RpcApiBadRequest(c, err.Error())
		return
	}

	var user model.UserInfo
	if err := database.GetDB().Where("user_name = ?", req.UserName).First(&user).Error; err != nil {
		RpcApiUnauthorized(c, "用户名或密码错误")
		return
	}

	if !password.CheckPassword(req.Password, user.Password) {
		RpcApiUnauthorized(c, "用户名或密码错误")
		return
	}

	database.GetDB().Model(&user).Update("last_active", time.Now())

	updateTime := ""
	if user.UpdateTime != nil {
		updateTime = user.UpdateTime.Format("2006-01-02T15:04:05")
	}

	RpcApiSuccess(c, gin.H{
			"id":         user.ID,
			"userName":   user.UserName,
			"lastActive": user.LastActive.Format("2006-01-02T15:04:05"),
			"createTime": user.CreateTime.Format("2006-01-02T15:04:05"),
			"loginToken": user.LoginToken,
			"apiToken":   user.ApiToken,
			"isAdmin":    user.IsAdmin,
			"updateTime": updateTime,
			"permission": user.Permission,
			"quotaQps":   user.QuotaQps,
		})
}

// HandleGetUserInfo 获取当前用户信息
func HandleGetUserInfo(c *gin.Context) {
	token := middleware.ExtractAuthTokenFromRequest(c)
	if token == "" {
		RpcApiError(c, -1, "请重新登录")
		return
	}

	user, err := middleware.FindUserByToken(token)
	if err != nil {
		RpcApiError(c, -1, "请重新登录")
		return
	}

	RpcApiSuccess(c, gin.H{
		"id":       user.ID,
		"userName": user.UserName,
		"isAdmin":  user.IsAdmin,
	})
}

// HandleSystemNotice 获取系统通知
func HandleSystemNotice(c *gin.Context) {
	cfgSvc, exists := c.Get("configService")
	var systemNotice string = ""
	if exists {
		if configSvc, ok := cfgSvc.(pkgconfig.Service); ok {
			systemNotice = configSvc.GetConfig(pkgconfig.ConfigKeySystemNotice)
		}
	}

	RpcApiSuccess(c, systemNotice)
}

// HandleSystemInfo 获取系统信息
func HandleSystemInfo(c *gin.Context) {
	yamlConfig := config.DefaultServerConfig()

	RpcApiSuccess(c, gin.H{
		"version":       "1.0.0",
		"buildTime":     "2026-03-20",
		"expireTime":    time.Now().AddDate(0, 1, 0).Format("2006-01-02 15:04"),
		"isExpire":      false,
		"mode":          yamlConfig.Mode,
		"cors":          yamlConfig.Cors,
		"port":          yamlConfig.Port,
		"host":          yamlConfig.Host,
		"database":      "postgresql",
		"clientVersion": "Go Rpc v1.0.0",
	})
}

// HandleFrontendListGroup 获取分组列表（前端兼容接口）
func HandleFrontendListGroup(c *gin.Context) {
	// Try to use groupRepo from context if available
	if groupRepo, exists := c.Get("groupRepo"); exists {
		if gr, ok := groupRepo.(repository.GroupRepository); ok {
			listGroupViaRepo(c, gr)
			return
		}
	}

	// Fallback: use direct DB
	db := database.GetDB()
	activeThreshold := time.Now().Add(-ClientInactiveThreshold)

	var stats []struct {
		ID                int64     `json:"id"`
		GroupName         string    `json:"groupName"`
		UserName          string    `json:"userName"`
		QuotaQpsGroup     float64   `json:"quotaQpsGroup"`
		QuotaQpsPerDevice float64   `json:"quotaQpsPerDevice"`
		CreateDate        time.Time `json:"createTime"`
		AvailableClients  int64     `json:"availableClients"`
		DisabledClients   int64     `json:"disabledClients"`
	}

	err := db.Table("group_config gc").
		Select(`
			gc.id, gc.group_name, gc.user_name,
			gc.quota_qps_group, gc.quota_qps_per_device, gc.create_date,
			SUM(CASE WHEN gd.last_active_time > ? THEN 1 ELSE 0 END) as available_clients,
			SUM(CASE WHEN gd.last_active_time <= ? THEN 1 ELSE 0 END) as disabled_clients
		`, activeThreshold, activeThreshold).
		Joins("LEFT JOIN group_device gd ON gc.group_name = gd.group_name").
		Group("gc.id, gc.group_name, gc.user_name, gc.quota_qps_group, gc.quota_qps_per_device, gc.create_date").
		Order("gc.create_date DESC").
		Scan(&stats).Error

	if err != nil {
		RpcApiInternalError(c, err.Error())
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
			CreateTime:        s.CreateDate.Format("2006-01-02T15:04:05"),
			AvailableClients:  s.AvailableClients,
			DisableClientSize: s.DisabledClients,
		})
	}

	RpcApiSuccess(c, vos)
}

// listGroupViaRepo 使用 GroupRepository 查询分组列表（前端格式）
func listGroupViaRepo(c *gin.Context, groupRepo repository.GroupRepository) {
	activeThreshold := time.Now().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	stats, err := groupRepo.GetGroupStats("", true, activeThreshold)
	if err != nil {
		RpcApiInternalError(c, err.Error())
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
			DisableClientSize: s.DisabledClients,
		})
	}

	RpcApiSuccess(c, vos)
}

// HandleFrontendAnonymousGroupList 获取匿名分组列表
func HandleFrontendAnonymousGroupList(c *gin.Context) {
	// Use groupRepo if available in context
	if groupRepo, exists := c.Get("groupRepo"); exists {
		if gr, ok := groupRepo.(repository.GroupRepository); ok {
			listAnonymousViaRepo(c, gr)
			return
		}
	}
	anonymousHandler := NewAnonymousGroupHandler(nil)
	anonymousHandler.List(c)
}

// listAnonymousViaRepo 使用 GroupRepository 查询匿名分组列表
func listAnonymousViaRepo(c *gin.Context, groupRepo repository.GroupRepository) {
	activeThreshold := time.Now().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	stats, err := groupRepo.FindAnonymousDeviceGroups(activeThreshold)
	if err != nil {
		RpcApiInternalError(c, err.Error())
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

	if len(vos) == 0 {
		vos = []AnonymousGroupVO{}
	}

	RpcApiSuccess(c, vos)
}

// HandleFrontendGroupDetail 获取分组详情
func HandleFrontendGroupDetail(c *gin.Context) {
	groupName := c.Query("groupName")
	if groupName == "" {
		RpcApiBadRequest(c, "groupName 参数必填")
		return
	}

	c.Params = append(c.Params, gin.Param{Key: "groupName", Value: groupName})

	// Use groupRepo if available in context
	if groupRepo, exists := c.Get("groupRepo"); exists {
		if gr, ok := groupRepo.(repository.GroupRepository); ok {
			groupHandler := NewGroupHandler(gr)
			groupHandler.GetDetail(c)
			return
		}
	}

	groupHandler := NewGroupHandler(nil)
	groupHandler.GetDetail(c)
}

// RegisterRequest 注册请求
type RegisterRequest struct {
	UserName string `form:"userName" binding:"required"`
	Password string `form:"password" binding:"required"`
}

// HandleRegister 处理注册请求
func HandleRegister(c *gin.Context) {
	cfgSvc, exists := c.Get("configService")
	if !exists {
		// 配置服务未初始化，使用默认值允许注册
	} else {
		if configSvc, ok := cfgSvc.(pkgconfig.Service); ok {
			if !configSvc.GetConfigBool(pkgconfig.ConfigKeyAllowRegister, true) {
				RpcApiForbidden(c, "当前不允许注册新用户")
				return
			}
		}
	}

	var req RegisterRequest
	if err := c.ShouldBind(&req); err != nil {
		RpcApiBadRequest(c, err.Error())
		return
	}

	var existingUser model.UserInfo
	if err := database.GetDB().Where("user_name = ?", req.UserName).First(&existingUser).Error; err == nil {
		RpcApiError(c, -1, "用户名已存在")
		return
	}

	now := time.Now()

	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		RpcApiInternalError(c, "密码加密失败")
		return
	}

	var defaultQps float64 = 100
	if cfgSvc != nil {
		if configSvc, ok := cfgSvc.(pkgconfig.Service); ok {
			defaultQps = configSvc.GetConfigFloat(pkgconfig.ConfigKeyDefaultQuotaUser, 100.0)
		}
	}

	user := model.UserInfo{
		UserName:   req.UserName,
		Password:   hashedPassword,
		QuotaQps:   defaultQps,
		IsAdmin:    false,
		ApiToken:   uuid.New().String(),
		LoginToken: uuid.New().String(),
		CreateTime: now,
		LastActive: now,
		UpdateTime: &now,
	}

	if err := database.GetDB().Create(&user).Error; err != nil {
		RpcApiInternalError(c, err.Error())
		return
	}

	RpcApiSuccess(c, gin.H{
		"id":       user.ID,
		"userName": user.UserName,
	})
}

// HandleUserAdd 添加用户（兼容 /rpc-api/user-info/add）
func HandleUserAdd(c *gin.Context) {
	var req AddUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		RpcApiBadRequest(c, err.Error())
		return
	}

	now := time.Now()

	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		RpcApiInternalError(c, "密码加密失败")
		return
	}

	user := model.UserInfo{
		UserName:   req.UserName,
		Password:   hashedPassword,
		QuotaQps:   req.QuotaQps,
		IsAdmin:    req.IsAdmin,
		ApiToken:   uuid.New().String(),
		LoginToken: uuid.New().String(),
		CreateTime: now,
		LastActive: now,
		UpdateTime: &now,
	}

	if err := database.GetDB().Create(&user).Error; err != nil {
		RpcApiInternalError(c, err.Error())
		return
	}

	RpcApiSuccess(c, user.ID)
}
