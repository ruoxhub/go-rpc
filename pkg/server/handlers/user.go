package handlers

import (
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// UserHandler 用户管理处理器
type UserHandler struct{}

// NewUserHandler 创建用户处理器
func NewUserHandler() *UserHandler {
	return &UserHandler{}
}

// ListUsersResponse 用户列表响应
type ListUsersResponse struct {
	Code    int            `json:"code"`
	Message string         `json:"message"`
	Data    []UserInfoVO   `json:"data"`
	Total   int64          `json:"total"`
}

type UserInfoVO struct {
	ID         int64   `json:"id"`
	UserName   string  `json:"userName"`
	QuotaQps   float64 `json:"quotaQps"`
	IsAdmin    bool    `json:"isAdmin"`
	CreateTime string  `json:"createTime"`
}

// List 获取用户列表
func (h *UserHandler) List(c *gin.Context) {
	var users []model.UserInfo
	result := database.GetDB().Find(&users)

	var vos []UserInfoVO
	for _, u := range users {
		vos = append(vos, UserInfoVO{
			ID:         u.ID,
			UserName:   u.UserName,
			QuotaQps:   u.QuotaQps,
			IsAdmin:    u.IsAdmin,
			CreateTime: u.CreateTime.Format("2006-01-02 15:04:05"),
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
		"total":   result.RowsAffected,
	})
}

// AddUserRequest 添加用户请求
type AddUserRequest struct {
	UserName string  `json:"userName" binding:"required"`
	Password string  `json:"password" binding:"required"`
	QuotaQps float64 `json:"quotaQps"`
	IsAdmin  bool    `json:"isAdmin"`
}

// Add 添加用户
func (h *UserHandler) Add(c *gin.Context) {
	var req AddUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	user := model.UserInfo{
		UserName:   req.UserName,
		Password:   req.Password, // TODO: 应该加密存储
		QuotaQps:   req.QuotaQps,
		IsAdmin:    req.IsAdmin,
		ApiToken:   uuid.New().String(),
		CreateTime: time.Now(),
		LastActive: time.Now(),
	}

	if err := database.GetDB().Create(&user).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success", "data": user.ID})
}

// UpdateUserQpsRequest 更新用户 QPS 请求
type UpdateUserQpsRequest struct {
	UserID   int64   `json:"userId" binding:"required"`
	QuotaQps float64 `json:"quotaQps" binding:"required"`
}

// UpdateQps 更新用户 QPS
func (h *UserHandler) UpdateQps(c *gin.Context) {
	var req UpdateUserQpsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	if err := database.GetDB().Model(&model.UserInfo{}).
		Where("id = ?", req.UserID).
		Update("quota_qps", req.QuotaQps).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

// DeleteUserRequest 删除用户请求
type DeleteUserRequest struct {
	UserID int64 `json:"userId" binding:"required"`
}

// Delete 删除用户
func (h *UserHandler) Delete(c *gin.Context) {
	var req DeleteUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	if err := database.GetDB().Delete(&model.UserInfo{}, req.UserID).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

// ChangePasswordRequest 修改密码请求
type ChangePasswordRequest struct {
	NewPassword string `json:"newPassword" binding:"required"`
}

// ChangePassword 修改密码
func (h *UserHandler) ChangePassword(c *gin.Context) {
	var req ChangePasswordRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// TODO: 从上下文中获取当前用户 ID
	// 这里简化处理，假设用户已登录
	if err := database.GetDB().Model(&model.UserInfo{}).
		Where("id = ?", 1). // 临时写死，实际应该从 token 中解析
		Update("password", req.NewPassword).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

// RefreshToken 刷新 API Token
func (h *UserHandler) RefreshToken(c *gin.Context) {
	// TODO: 从上下文中获取当前用户 ID
	newToken := uuid.New().String()

	if err := database.GetDB().Model(&model.UserInfo{}).
		Where("id = ?", 1). // 临时写死
		Update("api_token", newToken).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    gin.H{"apiToken": newToken},
	})
}

// GetCurrentUser 获取当前用户信息
func (h *UserHandler) GetCurrentUser(c *gin.Context) {
	// TODO: 从 token 中解析用户信息
	var user model.UserInfo
	if err := database.GetDB().First(&user, 1).Error; err != nil {
		c.JSON(404, gin.H{"code": 404, "message": "user not found"})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data": gin.H{
			"id":       user.ID,
			"userName": user.UserName,
			"apiToken": user.ApiToken,
			"isAdmin":  user.IsAdmin,
		},
	})
}
