package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/config"
	"github.com/mrh30000/go-rpc/pkg/server/middleware"
	"github.com/mrh30000/go-rpc/pkg/utils/password"
)

// UserHandler handles user management APIs.
type UserHandler struct {
	userRepo repository.UserRepository
}

func NewUserHandler(userRepo repository.UserRepository) *UserHandler {
	return &UserHandler{userRepo: userRepo}
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
	users, err := h.userRepo.List("id ASC")
	if err != nil {
		InternalError(c, err.Error())
		return
	}

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

	SuccessWithTotal(c, vos, int64(len(vos)))
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
		BadRequest(c, err.Error())
		return
	}

	count, err := h.userRepo.CountByUserName(req.UserName)
	if err != nil {
		InternalError(c, err.Error())
		return
	}
	if count > 0 {
		BadRequest(c, "user already exists")
		return
	}

	hashedPassword, err := password.HashPassword(req.Password)
	if err != nil {
		InternalError(c, "failed to hash password")
		return
	}

	var defaultQps float64 = 100
	cfgSvc, exists := c.Get("configService")
	if exists {
		if configSvc, ok := cfgSvc.(config.Service); ok {
			defaultQps = configSvc.GetConfigFloat(config.ConfigKeyDefaultQuotaUser, 100.0)
		}
	}

	qps := req.QuotaQps
	if qps <= 0 {
		qps = defaultQps
	}

	now := time.Now()
	user := model.UserInfo{
		UserName:   req.UserName,
		Password:   hashedPassword,
		QuotaQps:   qps,
		IsAdmin:    req.IsAdmin,
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

	Success(c, user.ID)
}

type UpdateUserQpsRequest struct {
	UserID   int64   `json:"userId" binding:"required"`
	QuotaQps float64 `json:"quotaQps" binding:"required"`
}

func (h *UserHandler) UpdateQps(c *gin.Context) {
	var req UpdateUserQpsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	user, err := h.userRepo.FindByID(req.UserID)
	if err != nil {
		InternalError(c, "user not found")
		return
	}

	if err := h.userRepo.UpdateFields(req.UserID, map[string]interface{}{
		"quota_qps": req.QuotaQps,
	}); err != nil {
		InternalError(c, err.Error())
		return
	}

	auditUpdateQps(c, "user", user.UserName, req.QuotaQps)
	Success(c, nil)
}

type DeleteUserRequest struct {
	UserID int64 `json:"userId" binding:"required"`
}

func (h *UserHandler) Delete(c *gin.Context) {
	var req DeleteUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	if err := h.userRepo.Delete(req.UserID); err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, nil)
}

type ChangePasswordRequest struct {
	NewPassword string `json:"newPassword" binding:"required"`
}

func (h *UserHandler) ChangePassword(c *gin.Context) {
	var req ChangePasswordRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		Unauthorized(c, "please login first")
		return
	}

	hashedPassword, err := password.HashPassword(req.NewPassword)
	if err != nil {
		InternalError(c, "failed to hash password")
		return
	}

	if err := h.userRepo.UpdateFields(user.ID, map[string]interface{}{
		"password": hashedPassword,
	}); err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, nil)
}

func (h *UserHandler) RefreshToken(c *gin.Context) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		Unauthorized(c, "please login first")
		return
	}

	newToken := uuid.New().String()
	if err := h.userRepo.UpdateFields(user.ID, map[string]interface{}{
		"api_token": newToken,
	}); err != nil {
		InternalError(c, err.Error())
		return
	}

	Success(c, gin.H{"apiToken": newToken})
}

func (h *UserHandler) GetCurrentUser(c *gin.Context) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		Unauthorized(c, "please login first")
		return
	}

	Success(c, gin.H{
			"id":       user.ID,
			"userName": user.UserName,
			"apiToken": user.ApiToken,
			"isAdmin":  user.IsAdmin,
			"quotaQps": user.QuotaQps,
		})
}
