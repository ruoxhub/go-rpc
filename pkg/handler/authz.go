package handler

import (
	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/handler/errorcode"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
)

func getAuthenticatedUser(c *gin.Context) (*model.UserInfo, bool) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists || user == nil {
		Unauthorized(c, "请先登录")
		return nil, false
	}
	return user, true
}

// groupAccessError 是一次分组访问校验失败的原因，携带业务错误码。
type groupAccessError struct {
	code    int
	message string
}

// checkGroupAccess 校验当前用户对分组的访问权限，但不写 HTTP 响应，
// 便于批量接口逐条收集失败原因。单条接口请用 authorizeGroupAccess。
func checkGroupAccess(c *gin.Context, groupName string, groupRepo repository.GroupRepository) (*model.GroupConfig, *groupAccessError) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists || user == nil {
		return nil, &groupAccessError{errorcode.Unauthorized, "请先登录"}
	}

	group, err := groupRepo.FindGroupByName(groupName)
	if err != nil {
		return nil, &groupAccessError{errorcode.InternalError, err.Error()}
	}
	if group == nil {
		return nil, &groupAccessError{errorcode.NotFound, "group not found"}
	}

	if !user.IsAdmin && group.UserName != user.UserName {
		return nil, &groupAccessError{errorcode.Forbidden, "无权访问该分组"}
	}

	return group, nil
}

// authorizeGroupAccess 校验权限，失败时直接写出错误响应。
func authorizeGroupAccess(c *gin.Context, groupName string, groupRepo repository.GroupRepository) (*model.GroupConfig, bool) {
	group, accessErr := checkGroupAccess(c, groupName, groupRepo)
	if accessErr != nil {
		Fail(c, accessErr.code, accessErr.message)
		return nil, false
	}
	return group, true
}
