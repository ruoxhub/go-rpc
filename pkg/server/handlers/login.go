package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/pkg/database"
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
// POST /sekiro-api/user-info/login
func HandleLogin(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBind(&req); err != nil {
		c.JSON(400, gin.H{
			"status":  -1,
			"message": err.Error(),
		})
		return
	}

	// 查询用户
	var user model.UserInfo
	if err := database.GetDB().Where("user_name = ?", req.UserName).First(&user).Error; err != nil {
		c.JSON(401, gin.H{
			"status":  -1,
			"message": "用户名或密码错误",
		})
		return
	}

	// 验证密码
	if !password.CheckPassword(req.Password, user.Password) {
		c.JSON(401, gin.H{
			"status":  -1,
			"message": "用户名或密码错误",
		})
		return
	}

	// 更新最后登录时间
	database.GetDB().Model(&user).Update("last_active", time.Now())

	// 返回用户信息（包含 loginToken 和 apiToken）
	updateTime := ""
	if user.UpdateTime != nil {
		updateTime = user.UpdateTime.Format("2006-01-02T15:04:05")
	}

	c.JSON(200, gin.H{
		"status":  0,
		"message": "success",
		"data": gin.H{
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
		},
	})
}

// HandleGetUserInfo 获取当前用户信息
// GET /sekiro-api/user-info/userInfo
func HandleGetUserInfo(c *gin.Context) {
	token := middleware.ExtractAuthTokenFromRequest(c)
	if token == "" {
		c.JSON(200, gin.H{
			"status":  -1,
			"message": "请重新登录",
			"ok":      false,
		})
		return
	}

	user, err := middleware.FindUserByToken(token)
	if err != nil {
		c.JSON(200, gin.H{
			"status":  -1,
			"message": "请重新登录",
			"ok":      false,
		})
		return
	}

	c.JSON(200, gin.H{
		"status":  0,
		"message": "success",
		"data": gin.H{
			"id":       user.ID,
			"userName": user.UserName,
			"isAdmin":  user.IsAdmin,
		},
		"ok": true,
	})
}

// HandleSystemNotice 获取系统通知
// GET /sekiro-api/system/systemNotice
func HandleSystemNotice(c *gin.Context) {
	// 从 context 获取配置服务
	cfgSvc, exists := c.Get("configService")
	var systemNotice string = ""
	if exists {
		if configSvc, ok := cfgSvc.(pkgconfig.Service); ok {
			systemNotice = configSvc.GetConfig(pkgconfig.ConfigKeySystemNotice)
		}
	}

	c.JSON(200, gin.H{
		"status":  0,
		"message": "success",
		"data":    systemNotice,
	})
}

// HandleSystemInfo 获取系统信息
// GET /sekiro-api/system/systemInfo
func HandleSystemInfo(c *gin.Context) {
	yamlConfig := config.DefaultConfig()

	c.JSON(200, gin.H{
		"status":  0,
		"message": "success",
		"data": gin.H{
			"version":       "1.0.0",
			"buildTime":     "2026-03-20",
			"expireTime":    time.Now().AddDate(0, 1, 0).Format("2006-01-02 15:04"), // 一个月后过期
			"isExpire":      false,
			"mode":          yamlConfig.Mode,
			"cors":          yamlConfig.Cors,
			"port":          yamlConfig.Port,
			"host":          yamlConfig.Host,
			"database":      "postgresql",
			"clientVersion": "Go Rpc v1.0.0",
		},
	})
}

// HandleFrontendListGroup 获取分组列表（前端兼容接口）
// GET /sekiro-api/frontend/listGroup
func HandleFrontendListGroup(c *gin.Context) {
	db := database.GetDB()
	activeThreshold := time.Now().Add(-ClientInactiveThreshold)

	// 使用优化版本：单次 JOIN + GROUP BY 查询替代 N+1 查询
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
			gc.id,
			gc.group_name,
			gc.user_name,
			gc.quota_qps_group,
			gc.quota_qps_per_device,
			gc.create_date,
			SUM(CASE WHEN gd.last_active_time > ? THEN 1 ELSE 0 END) as available_clients,
			SUM(CASE WHEN gd.last_active_time <= ? THEN 1 ELSE 0 END) as disabled_clients
		`, activeThreshold, activeThreshold).
		Joins("LEFT JOIN group_device gd ON gc.group_name = gd.group_name").
		Group("gc.id, gc.group_name, gc.user_name, gc.quota_qps_group, gc.quota_qps_per_device, gc.create_date").
		Order("gc.create_date DESC").
		Scan(&stats).Error

	if err != nil {
		c.JSON(500, gin.H{
			"status":  -1,
			"message": err.Error(),
		})
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
			CreateTime:        s.CreateDate.Format("2006-01-02T15:04:05"),
			AvailableClients:  s.AvailableClients,
			DisableClientSize: s.DisabledClients,
		})
	}

	c.JSON(200, gin.H{
		"status":  0,
		"message": "success",
		"data":    vos,
		"ok":      true,
	})
}

// HandleFrontendAnonymousGroupList 获取匿名分组列表（前端兼容接口）
// GET /sekiro-api/frontend/anonymousGroupList
func HandleFrontendAnonymousGroupList(c *gin.Context) {
	anonymousHandler := NewAnonymousGroupHandler()
	anonymousHandler.ListOptimized(c)
}

// HandleFrontendGroupDetail 获取分组详情（前端兼容接口）
// GET /sekiro-api/frontend/groupDetail?groupName=xxx
func HandleFrontendGroupDetail(c *gin.Context) {
	groupName := c.Query("groupName")
	if groupName == "" {
		c.JSON(400, gin.H{
			"status":  -1,
			"message": "groupName 参数必填",
		})
		return
	}

	// 将 groupName 设置为 URL 参数，以便 GetDetail 方法可以读取
	c.Params = append(c.Params, gin.Param{Key: "groupName", Value: groupName})

	groupHandler := NewGroupHandler()
	groupHandler.GetDetail(c)
}

// RegisterRequest 注册请求
type RegisterRequest struct {
	UserName string `form:"userName" binding:"required"`
	Password string `form:"password" binding:"required"`
}

// HandleRegister 处理注册请求
// POST /sekiro-api/user-info/register
func HandleRegister(c *gin.Context) {
	// 检查是否允许注册
	cfgSvc, exists := c.Get("configService")
	if !exists {
		// 配置服务未初始化，使用默认值允许注册
	} else {
		if configSvc, ok := cfgSvc.(pkgconfig.Service); ok {
			if !configSvc.GetConfigBool(pkgconfig.ConfigKeyAllowRegister, true) {
				c.JSON(403, gin.H{
					"status":  -1,
					"message": "当前不允许注册新用户",
				})
				return
			}
		}
	}

	var req RegisterRequest
	if err := c.ShouldBind(&req); err != nil {
		c.JSON(400, gin.H{
			"status":  -1,
			"message": err.Error(),
		})
		return
	}

	// 检查用户是否已存在
	var existingUser model.UserInfo
	if err := database.GetDB().Where("user_name = ?", req.UserName).First(&existingUser).Error; err == nil {
		c.JSON(200, gin.H{
			"status":  -1,
			"message": "用户名已存在",
		})
		return
	}

	now := time.Now()

	// 哈希密码
	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		c.JSON(500, gin.H{
			"status":  -1,
			"message": "密码加密失败",
		})
		return
	}

	// 获取默认 QPS 配置
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
		c.JSON(500, gin.H{
			"status":  -1,
			"message": err.Error(),
		})
		return
	}

	c.JSON(200, gin.H{
		"status":  0,
		"message": "注册成功",
		"data": gin.H{
			"id":       user.ID,
			"userName": user.UserName,
		},
	})
}

// HandleUserAdd 添加用户（兼容 /sekiro-api/user-info/add）
func HandleUserAdd(c *gin.Context) {
	var req AddUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{
			"status":  -1,
			"message": err.Error(),
		})
		return
	}

	now := time.Now()

	// 哈希密码
	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		c.JSON(500, gin.H{
			"status":  -1,
			"message": "密码加密失败",
		})
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
		c.JSON(500, gin.H{
			"status":  -1,
			"message": err.Error(),
		})
		return
	}

	c.JSON(200, gin.H{
		"status":  0,
		"message": "success",
		"data":    user.ID,
	})
}
