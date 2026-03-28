package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"github.com/sekiro-go/sekiro-go/pkg/server/middleware"
	"github.com/sekiro-go/sekiro-go/pkg/utils/password"
)

// UserHandler handles user management APIs.
type UserHandler struct{}

func NewUserHandler() *UserHandler {
	return &UserHandler{}
}

type ListUsersResponse struct {
	Code    int          `json:"code"`
	Message string       `json:"message"`
	Data    []UserInfoVO `json:"data"`
	Total   int64        `json:"total"`
}

type UserInfoVO struct {
	ID         int64   `json:"id"`
	UserName   string  `json:"userName"`
	QuotaQps   float64 `json:"quotaQps"`
	IsAdmin    bool    `json:"isAdmin"`
	CreateTime string  `json:"createTime"`
}

func (h *UserHandler) List(c *gin.Context) {
	var users []model.UserInfo
	result := database.GetDB().Order("id ASC").Find(&users)

	vos := make([]UserInfoVO, 0, len(users))
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

type AddUserRequest struct {
	UserName string  `json:"userName" binding:"required"`
	Password string  `json:"password" binding:"required"`
	QuotaQps float64 `json:"quotaQps"`
	IsAdmin  bool    `json:"isAdmin"`
}

func (h *UserHandler) Add(c *gin.Context) {
	var req AddUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	var count int64
	if err := database.GetDB().Model(&model.UserInfo{}).
		Where("user_name = ?", req.UserName).
		Count(&count).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}
	if count > 0 {
		c.JSON(400, gin.H{"code": 400, "message": "user already exists"})
		return
	}

	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		c.JSON(500, gin.H{"code": 500, "message": "failed to hash password"})
		return
	}

	now := time.Now()
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
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success", "data": user.ID})
}

type UpdateUserQpsRequest struct {
	UserID   int64   `json:"userId" binding:"required"`
	QuotaQps float64 `json:"quotaQps" binding:"required"`
}

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

type DeleteUserRequest struct {
	UserID int64 `json:"userId" binding:"required"`
}

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

type ChangePasswordRequest struct {
	NewPassword string `json:"newPassword" binding:"required"`
}

func (h *UserHandler) ChangePassword(c *gin.Context) {
	var req ChangePasswordRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		c.JSON(401, gin.H{"code": 401, "message": "please login first"})
		return
	}

	hashedPassword, err := password.HashPassword(req.NewPassword)
	if err != nil {
		c.JSON(500, gin.H{"code": 500, "message": "failed to hash password"})
		return
	}

	if err := database.GetDB().Model(&model.UserInfo{}).
		Where("id = ?", user.ID).
		Updates(map[string]interface{}{
			"password":    hashedPassword,
			"update_time": time.Now(),
		}).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{"code": 0, "message": "success"})
}

func (h *UserHandler) RefreshToken(c *gin.Context) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		c.JSON(401, gin.H{"code": 401, "message": "please login first"})
		return
	}

	newToken := uuid.New().String()
	if err := database.GetDB().Model(&model.UserInfo{}).
		Where("id = ?", user.ID).
		Updates(map[string]interface{}{
			"api_token":   newToken,
			"update_time": time.Now(),
		}).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    gin.H{"apiToken": newToken},
	})
}

func (h *UserHandler) GetCurrentUser(c *gin.Context) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		c.JSON(401, gin.H{"code": 401, "message": "please login first"})
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
			"quotaQps": user.QuotaQps,
		},
	})
}
