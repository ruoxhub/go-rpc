package handlers

import (
	"fmt"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"github.com/sekiro-go/sekiro-go/pkg/server/middleware"
)

// AuditAction 定义审计操作类型
type AuditAction string

const (
	AuditActionDeleteGroup   AuditAction = "DELETE_GROUP"
	AuditActionDeleteDevice  AuditAction = "DELETE_DEVICE"
	AuditActionDisableDevice AuditAction = "DISABLE_DEVICE"
	AuditActionDeleteAction  AuditAction = "DELETE_ACTION"
	AuditActionUpdateQps     AuditAction = "UPDATE_QPS"
	AuditActionUpdateConfig  AuditAction = "UPDATE_CONFIG"
	AuditActionConvertGroup  AuditAction = "CONVERT_GROUP"
)

// logAudit 记录审计日志
func logAudit(c *gin.Context, action AuditAction, resource string, detail string) {
	user, exists := middleware.GetCurrentUser(c)
	if !exists {
		return
	}

	audit := model.SysLog{
		Username:   user.UserName,
		Operation:  string(action),
		Params:     detail,
		MethodName: resource,
		CreateTime: time.Now(),
	}

	database.GetDB().Create(&audit)
}

// 审计日志辅助函数

// auditDeleteGroup 记录删除分组的审计日志
func auditDeleteGroup(c *gin.Context, groupName string) {
	logAudit(c, AuditActionDeleteGroup, "group_config", "删除分组："+groupName)
}

// auditDeleteDevice 记录删除设备的审计日志
func auditDeleteDevice(c *gin.Context, groupName, deviceID string) {
	logAudit(c, AuditActionDeleteDevice, "group_device", "删除设备 - 分组："+groupName+", 设备 ID："+deviceID)
}

// auditDisableDevice 记录禁用设备的审计日志
func auditDisableDevice(c *gin.Context, groupName, deviceID string) {
	logAudit(c, AuditActionDisableDevice, "group_device", "禁用设备 - 分组："+groupName+", 设备 ID："+deviceID)
}

// auditDeleteAction 记录删除 Action 的审计日志
func auditDeleteAction(c *gin.Context, groupName, actionName string) {
	logAudit(c, AuditActionDeleteAction, "group_actions", "删除 Action - 分组："+groupName+", Action："+actionName)
}

// auditUpdateQps 记录更新 QPS 的审计日志
func auditUpdateQps(c *gin.Context, targetType, targetName string, newQps float64) {
	logAudit(c, AuditActionUpdateQps, targetType, fmt.Sprintf("更新 %s QPS - 名称：%s, 新 QPS：%.2f", targetType, targetName, newQps))
}

// auditUpdateConfig 记录更新系统配置的审计日志
func auditUpdateConfig(c *gin.Context, key, value string) {
	logAudit(c, AuditActionUpdateConfig, "sys_config", "更新配置 - Key："+key)
}

// auditConvertGroup 记录转换匿名分组为正式分组的审计日志
func auditConvertGroup(c *gin.Context, anonymousGroup, newGroup string) {
	logAudit(c, AuditActionConvertGroup, "group_config", "转换匿名分组 - 原分组："+anonymousGroup+", 新分组："+newGroup)
}
