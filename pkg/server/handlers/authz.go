package handlers

import (
	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/middleware"
)

func getAuthenticatedUser(c *gin.Context) (*model.UserInfo, bool) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists || user == nil {
		Unauthorized(c, "请先登录")
		return nil, false
	}
	return user, true
}

func authorizeGroupAccess(c *gin.Context, groupName string, groupRepo repository.GroupRepository) (*model.GroupConfig, bool) {
	user, ok := getAuthenticatedUser(c)
	if !ok {
		return nil, false
	}

	group, err := groupRepo.FindGroupByName(groupName)
	if err != nil {
		InternalError(c, err.Error())
		return nil, false
	}
	if group == nil {
		NotFound(c, "group not found")
		return nil, false
	}

	if !user.IsAdmin && group.UserName != user.UserName {
		Forbidden(c, "无权访问该分组")
		return nil, false
	}

	return group, true
}
