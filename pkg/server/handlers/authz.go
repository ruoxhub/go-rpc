package handlers

import (
	"errors"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/middleware"
	"gorm.io/gorm"
)

func getAuthenticatedUser(c *gin.Context) (*model.UserInfo, bool) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists || user == nil {
		c.JSON(401, gin.H{"code": 401, "message": "请先登录"})
		return nil, false
	}
	return user, true
}

func authorizeGroupAccess(c *gin.Context, groupName string) (*model.GroupConfig, bool) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return nil, false
	}

	var group model.GroupConfig
	if err := database.GetDB().Where("group_name = ?", groupName).First(&group).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			c.JSON(404, gin.H{"code": 404, "message": "group not found"})
			return nil, false
		}
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return nil, false
	}

	if !user.IsAdmin && group.UserName != user.UserName {
		c.JSON(403, gin.H{"code": 403, "message": "无权访问该分组"})
		return nil, false
	}

	return &group, true
}
