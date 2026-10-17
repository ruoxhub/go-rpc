package handler

import (
	"fmt"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// sysLogRepoVar is a package-level repository reference used by audit functions.
// It is set during initialization in SetupWebRoutes or bootstrap.
var sysLogRepoVar repository.SysLogRepository

// SetSysLogRepository sets the SysLogRepository for audit logging.
func SetSysLogRepository(repo repository.SysLogRepository) {
	sysLogRepoVar = repo
}

// AuditAction 定义审计操作类型
type AuditAction string

const (
	AuditActionDeleteGroup   AuditAction = "DELETE_GROUP"
	AuditActionDeleteDevice  AuditAction = "DELETE_DEVICE"
	AuditActionDeleteAction  AuditAction = "DELETE_ACTION"
	AuditActionUpdateQps     AuditAction = "UPDATE_QPS"
	AuditActionUpdateConfig  AuditAction = "UPDATE_CONFIG"
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

	if sysLogRepoVar != nil {
		sysLogRepoVar.Create(&audit)
	}
}

// 审计日志辅助函数

func auditDeleteGroup(c *gin.Context, groupName string) {
	logAudit(c, AuditActionDeleteGroup, "group_config", "删除分组："+groupName)
}

func auditDeleteDevice(c *gin.Context, groupName, deviceID string) {
	logAudit(c, AuditActionDeleteDevice, "group_device", "删除设备 - 分组："+groupName+", 设备 ID："+deviceID)
}

func auditDeleteAction(c *gin.Context, groupName, actionName string) {
	logAudit(c, AuditActionDeleteAction, "group_actions", "删除 Action - 分组："+groupName+", Action："+actionName)
}

func auditUpdateQps(c *gin.Context, targetType, targetName string, newQps float64) {
	logAudit(c, AuditActionUpdateQps, targetType, fmt.Sprintf("更新 %s QPS - 名称：%s, 新 QPS：%.2f", targetType, targetName, newQps))
}

func auditUpdateConfig(c *gin.Context, key, value string) {
	logAudit(c, AuditActionUpdateConfig, "sys_config", "更新配置 - Key："+key)
}

