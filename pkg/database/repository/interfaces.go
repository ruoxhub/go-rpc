// Package repository implements the Repository pattern for data access.
// Each repository interface encapsulates data access logic for an aggregate root,
// enabling testability through mock implementations.
package repository

import (
	"github.com/mrh30000/go-rpc/pkg/model"
)

// UserRepository handles user data access.
type UserRepository interface {
	FindByID(id int64) (*model.UserInfo, error)
	FindByUserName(name string) (*model.UserInfo, error)
	FindByToken(token string) (*model.UserInfo, error)
	Create(user *model.UserInfo) error
	Update(user *model.UserInfo) error
	UpdateFields(id int64, fields map[string]interface{}) error
	Delete(id int64) error
	List(order string) ([]model.UserInfo, error)
	CountByUserName(name string) (int64, error)
}

// GroupStats holds group statistics with device counts.
type GroupStats struct {
	ID                int64
	GroupName         string
	UserName          string
	QuotaQpsGroup     float64
	QuotaQpsPerDevice float64
	CreateDate        string
	AvailableClients  int64
	DisabledClients   int64
}

// AnonymousGroupStats holds anonymous group statistics.
type AnonymousGroupStats struct {
	GroupName        string
	TotalClients     int64
	AvailableClients int64
	DisabledClients  int64
}

// GroupRepository handles group, device, and action data access.
type GroupRepository interface {
	// Group operations
	FindGroupByName(name string) (*model.GroupConfig, error)
	FindAllGroups() ([]model.GroupConfig, error)
	CreateGroup(group *model.GroupConfig) error
	UpdateGroup(name string, updates map[string]interface{}) error
	DeleteGroup(name string) error
	CountGroups() (int64, error)

	// Group statistics
	GetGroupStats(userName string, isAdmin bool, activeThreshold string) ([]GroupStats, error)
	GetGroupDeviceStats(name string, activeThreshold string) (available, disabled int64, err error)

	// Device operations
	FindDevicesByGroup(name string) ([]model.GroupDevice, error)
	FindDevice(groupName, deviceID string) (*model.GroupDevice, error)
	CreateDevice(device *model.GroupDevice) error
	UpdateDevice(groupName, deviceID string, updates map[string]interface{}) error
	DeleteDevice(groupName, deviceID string) error
	DeleteDevicesByGroup(name string) error
	CountOnlineDevices(since string) (int64, error)
	CountDevicesByGroup(name string) (int64, error)

	// Action operations
	FindActionsByGroup(name string) ([]model.GroupAction, error)
	FindAction(groupName, actionName string) (*model.GroupAction, error)
	CreateAction(action *model.GroupAction) error
	DeleteAction(groupName, actionName string) error
	DeleteActionsByGroup(name string) error

	// Anonymous group operations
	FindAnonymousDeviceGroups(activeThreshold string) ([]AnonymousGroupStats, error)
	IsAnonymousGroup(name string) (bool, error)
	DeleteAnonymousGroupDevices(name string) (int64, error)

	// Transaction support
	WithTx(tx interface{}) GroupRepository
}

// SysConfigRepository handles system configuration data access.
type SysConfigRepository interface {
	FindAll() ([]model.SysConfig, error)
	FindByKey(key string) (*model.SysConfig, error)
	Upsert(key, value string) error
}

// ServerNodeRepository handles server node data access.
type ServerNodeRepository interface {
	FindAll() ([]model.ServerNode, error)
}

// SysLogRepository handles audit log data access.
type SysLogRepository interface {
	Create(log *model.SysLog) error
	FindAll(query SysLogQuery) ([]model.SysLog, int64, error)
}

// SysLogQuery holds audit log query parameters.
type SysLogQuery struct {
	Level     string
	StartTime string
	EndTime   string
	Keyword   string
	Page      int
	PageSize  int
}

// TraceRepository handles trace record data access.
type TraceRepository interface {
	FindByQuery(query model.TraceQuery) ([]model.TraceRecord, int64, error)
	FindByTraceID(traceID string) ([]model.TraceRecord, error)
	FindFirstByTraceID(traceID string) (*model.TraceRecord, error)
	GetStats(group, api, startTime, endTime string) (*TraceStats, error)
	GetTimeline(group, api string, limit int) ([]model.TraceRecord, error)
}

// TraceStats holds trace statistics.
type TraceStats struct {
	Total        int64
	SuccessCount int64
	FailureCount int64
	SuccessRate  float64
	AvgLatency   float64
	MaxLatency   int64
	MinLatency   int64
}

// AlertRepository handles alert rule and history data access.
type AlertRepository interface {
	// Rules
	FindRuleByID(id int64) (*model.AlertRule, error)
	FindRulesByQuery(query model.AlertRuleQuery) ([]model.AlertRule, int64, error)
	FindAllEnabledRules() ([]model.AlertRule, error)
	CreateRule(rule *model.AlertRule) error
	UpdateRule(rule *model.AlertRule) error
	DeleteRule(id int64) error

	// History
	FindHistoryByQuery(query model.AlertHistoryQuery) ([]model.AlertHistory, int64, error)
	CreateHistory(history *model.AlertHistory) error
}

// MetricRepository handles metric data access.
type MetricRepository interface {
	FindMetrics(table, name, startTime, endTime string, limit int) ([]model.MetricMinute, error)
	FindMetricTags() ([]model.MetricTag, error)
	GetDashboardData() (*DashboardData, error)
	GetLatencyPercentiles(group, api, startTime, endTime string) ([]model.MetricMinute, error)
}

// DashboardData holds dashboard statistics.
type DashboardData struct {
	TotalCalls    int64
	OnlineDevices int64
	TotalGroups   int64
	TotalUsers    int64
}
