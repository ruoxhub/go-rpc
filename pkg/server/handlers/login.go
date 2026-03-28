package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/sekiro-go/sekiro-go/internal/config"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	pkgconfig "github.com/sekiro-go/sekiro-go/pkg/server/config"
	"github.com/sekiro-go/sekiro-go/pkg/utils/password"
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
	// 从 header 获取 token
	token := c.GetHeader("sekiro-token")
	if token == "" {
		c.JSON(200, gin.H{
			"status":  -1,
			"message": "请重新登录",
			"ok":      false,
		})
		return
	}

	// 查询用户
	var user model.UserInfo
	if err := database.GetDB().Where("api_token = ?", token).First(&user).Error; err != nil {
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
			"clientVersion": "Go Sekiro v1.0.0",
		},
	})
}

// HandleFrontendListGroup 获取分组列表（前端兼容接口）
// GET /sekiro-api/frontend/listGroup
func HandleFrontendListGroup(c *gin.Context) {
	var groups []model.GroupConfig
	database.GetDB().Find(&groups)

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
			CreateTime:        g.CreateDate.Format("2006-01-02T15:04:05"),
			AvailableClients:  availableCount,
			DisableClientSize: disabledCount,
		})
	}

	c.JSON(200, gin.H{
		"status":  0,
		"message": "success",
		"data":    vos,
		"ok":      true,
	})
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
