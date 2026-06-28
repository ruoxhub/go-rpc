package handler

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/mrh30000/go-rpc/internal/config"
	pkgconfig "github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/handler/errorcode"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/utils/password"
)

var (
	loginUserRepo  repository.UserRepository
	loginGroupRepo repository.GroupRepository
)

// SetUserRepository sets the UserRepository for login/register handlers.
func SetUserRepository(r repository.UserRepository) { loginUserRepo = r }

// SetLoginGroupRepository sets the GroupRepository for frontend list handlers.
func SetLoginGroupRepository(r repository.GroupRepository) { loginGroupRepo = r }

// LoginRequest 登录请求
type LoginRequest struct {
	UserName string `form:"userName" binding:"required"`
	Password string `form:"password" binding:"required"`
}

// HandleLogin 处理登录请求
func HandleLogin(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBind(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	if loginUserRepo == nil {
		InternalError(c, "user repository not available")
		return
	}

	user, err := loginUserRepo.FindByUserName(req.UserName)
	if err != nil || user == nil {
		Unauthorized(c, "用户名或密码错误")
		return
	}

	if !password.CheckPassword(req.Password, user.Password) {
		Unauthorized(c, "用户名或密码错误")
		return
	}

	loginUserRepo.UpdateFields(user.ID, map[string]interface{}{"last_active": time.Now()})

	updateTime := ""
	if user.UpdateTime != nil {
		updateTime = user.UpdateTime.Format("2006-01-02T15:04:05")
	}

	OK(c, gin.H{
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
	user, ok := middleware.GetCurrentUser(c)
	if !ok || user == nil {
		Unauthorized(c, "请重新登录")
		return
	}

	OK(c, gin.H{
		"id":       user.ID,
		"userName": user.UserName,
		"isAdmin":  user.IsAdmin,
	})
}

// HandleSystemNotice 获取系统通知
func HandleSystemNotice(c *gin.Context) {
	var systemNotice string
	if cfgSvc, exists := c.Get("configService"); exists {
		if svc, ok := cfgSvc.(pkgconfig.Service); ok {
			systemNotice = svc.GetConfig(pkgconfig.ConfigKeySystemNotice)
		}
	}
	OK(c, systemNotice)
}

// HandleSystemInfo 获取系统信息
func HandleSystemInfo(c *gin.Context) {
	yamlConfig := config.DefaultServerConfig()

	OK(c, gin.H{
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
	gr := loginGroupRepo
	if gr == nil {
		// Try to use groupRepo from context if available
		if repo, exists := c.Get("groupRepo"); exists {
			if r, ok := repo.(repository.GroupRepository); ok {
				gr = r
			}
		}
	}
	if gr != nil {
		listGroupViaRepo(c, gr)
		return
	}

	InternalError(c, "group repository not available")
}

// listGroupViaRepo 使用 GroupRepository 查询分组列表（前端格式）
func listGroupViaRepo(c *gin.Context, groupRepo repository.GroupRepository) {
	activeThreshold := time.Now().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	stats, err := groupRepo.GetGroupStats("", true, activeThreshold)
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
			DisableClientSize: s.DisabledClients,
		})
	}

	OK(c, vos)
}

// HandleFrontendAnonymousGroupList 获取匿名分组列表
func HandleFrontendAnonymousGroupList(c *gin.Context) {
	if clientManager, exists := c.Get("clientManager"); exists {
		if cm, ok := clientManager.(anonymousClientManager); ok {
			OK(c, buildAnonymousGroupVOs(cm))
			return
		}
	}

	// Use groupRepo if available in context
	if groupRepo, exists := c.Get("groupRepo"); exists {
		if gr, ok := groupRepo.(repository.GroupRepository); ok {
			listAnonymousViaRepo(c, gr)
			return
		}
	}
	anonymousHandler := NewAnonymousGroupHandler(nil, nil, nil)
	anonymousHandler.List(c)
}

// listAnonymousViaRepo 使用 GroupRepository 查询匿名分组列表
func listAnonymousViaRepo(c *gin.Context, groupRepo repository.GroupRepository) {
	activeThreshold := time.Now().Add(-ClientInactiveThreshold).Format("2006-01-02 15:04:05")
	stats, err := groupRepo.FindAnonymousDeviceGroups(activeThreshold)
	if err != nil {
		InternalError(c, err.Error())
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

	OK(c, vos)
}

// HandleFrontendGroupDetail 获取分组详情
func HandleFrontendGroupDetail(c *gin.Context) {
	groupName := c.Query("groupName")
	if groupName == "" {
		BadRequest(c, "groupName 参数必填")
		return
	}

	c.Params = append(c.Params, gin.Param{Key: "groupName", Value: groupName})

	// Use groupRepo if available in context
	if groupRepo, exists := c.Get("groupRepo"); exists {
		if gr, ok := groupRepo.(repository.GroupRepository); ok {
			groupHandler := NewGroupHandler(gr, nil)
			groupHandler.GetDetail(c)
			return
		}
	}

	groupHandler := NewGroupHandler(nil, nil)
	groupHandler.GetDetail(c)
}

// RegisterRequest 注册请求
type RegisterRequest struct {
	UserName string `form:"userName" binding:"required"`
	Password string `form:"password" binding:"required"`
}

// HandleRegister 处理注册请求
func HandleRegister(c *gin.Context) {
	var configSvc pkgconfig.Service
	if cfgSvc, exists := c.Get("configService"); exists {
		configSvc, _ = cfgSvc.(pkgconfig.Service)
	}

	if configSvc != nil && !configSvc.GetConfigBool(pkgconfig.ConfigKeyAllowRegister, true) {
		Fail(c, errorcode.RegisterDisabled, "当前不允许注册新用户")
		return
	}

	var req RegisterRequest
	if err := c.ShouldBind(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	if loginUserRepo == nil {
		InternalError(c, "user repository not available")
		return
	}

	existing, err := loginUserRepo.FindByUserName(req.UserName)
	if err == nil && existing != nil {
		BadRequest(c, "用户名已存在")
		return
	}

	now := time.Now()

	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		Fail(c, errorcode.EncryptFailed, "密码加密失败")
		return
	}

	var defaultQps float64 = 100
	if configSvc != nil {
		defaultQps = configSvc.GetConfigFloat(pkgconfig.ConfigKeyDefaultQuotaUser, 100.0)
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

	if err := loginUserRepo.Create(&user); err != nil {
		InternalError(c, err.Error())
		return
	}

	OK(c, gin.H{
		"id":       user.ID,
		"userName": user.UserName,
	})
}

// HandleUserAdd 添加用户（兼容 /rpc-api/user-info/add）
func HandleUserAdd(c *gin.Context) {
	var req AddUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	if loginUserRepo == nil {
		InternalError(c, "user repository not available")
		return
	}

	now := time.Now()

	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		Fail(c, errorcode.EncryptFailed, "密码加密失败")
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

	if err := loginUserRepo.Create(&user); err != nil {
		InternalError(c, err.Error())
		return
	}

	OK(c, user.ID)
}

// LoginHandler handles login and registration requests with injected dependencies.
type LoginHandler struct {
	userRepo repository.UserRepository
}

// NewLoginHandler creates a LoginHandler with explicit dependency injection.
func NewLoginHandler(userRepo repository.UserRepository) *LoginHandler {
	return &LoginHandler{userRepo: userRepo}
}

// HandleLogin handles login requests.
func (h *LoginHandler) HandleLogin(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBind(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}
	if h.userRepo == nil {
		InternalError(c, "user repository not available")
		return
	}
	user, err := h.userRepo.FindByUserName(req.UserName)
	if err != nil || user == nil {
		Unauthorized(c, "用户名或密码错误")
		return
	}
	if !password.CheckPassword(req.Password, user.Password) {
		Unauthorized(c, "用户名或密码错误")
		return
	}
	h.userRepo.UpdateFields(user.ID, map[string]interface{}{"last_active": time.Now()})
	updateTime := ""
	if user.UpdateTime != nil {
		updateTime = user.UpdateTime.Format("2006-01-02T15:04:05")
	}
	OK(c, gin.H{
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

// HandleRegister handles user registration requests.
func (h *LoginHandler) HandleRegister(c *gin.Context) {
	var req RegisterRequest
	if err := c.ShouldBind(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}
	if h.userRepo == nil {
		InternalError(c, "user repository not available")
		return
	}
	existing, err := h.userRepo.FindByUserName(req.UserName)
	if err == nil && existing != nil {
		BadRequest(c, "用户名已存在")
		return
	}
	now := time.Now()
	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		Fail(c, errorcode.EncryptFailed, "密码加密失败")
		return
	}
	var defaultQps float64 = 100
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
	if err := h.userRepo.Create(&user); err != nil {
		InternalError(c, err.Error())
		return
	}
	OK(c, gin.H{
		"id":       user.ID,
		"userName": user.UserName,
	})
}
