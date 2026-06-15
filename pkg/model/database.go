package model

import "time"

// UserInfo 用户信息
type UserInfo struct {
	ID         int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	UserName   string    `json:"user_name" gorm:"size:64"`
	Password   string    `json:"-" gorm:"size:64"`
	LastActive time.Time `json:"last_active" gorm:"not null;default:CURRENT_TIMESTAMP"`
	CreateTime time.Time `json:"create_time" gorm:"default:CURRENT_TIMESTAMP"`
	LoginToken string    `json:"-" gorm:"size:64"`
	// ApiToken 在 PostgreSQL 侧通过部分唯一索引保证非空唯一（见 migration.sql 中 uniq_user_info_api_token）。
	// 这里只声明常规索引以避免 GORM AutoMigrate 生成冲突的全局唯一索引。
	ApiToken   string     `json:"api_token" gorm:"size:64;default:'';index:idx_user_info_api_token"`
	IsAdmin    bool       `json:"is_admin" gorm:"not null;default:false"`
	UpdateTime *time.Time `json:"update_time" gorm:"type:timestamp"`
	Permission string     `json:"permission" gorm:"type:text;default:''"`
	QuotaQps   float64    `json:"quota_qps" gorm:"not null;default:10"`
}

func (UserInfo) TableName() string {
	return "user_info"
}

// SysConfig 系统配置
type SysConfig struct {
	ID            int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	ConfigComment string    `json:"config_comment" gorm:"size:128"`
	ConfigKey     string    `json:"config_key" gorm:"size:64"`
	ConfigValue   string    `json:"config_value" gorm:"size:1024"`
	CreateTime    time.Time `json:"create_time" gorm:"default:CURRENT_TIMESTAMP"`
}

func (SysConfig) TableName() string {
	return "sys_config"
}

// SysLog 系统日志
type SysLog struct {
	ID         int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	Username   string    `json:"username" gorm:"size:100"`
	Operation  string    `json:"operation" gorm:"size:200"`
	Params     string    `json:"params" gorm:"size:500"`
	MethodName string    `json:"method_name" gorm:"size:200"`
	CreateTime time.Time `json:"create_time" gorm:"default:CURRENT_TIMESTAMP"`
}

func (SysLog) TableName() string {
	return "sys_log"
}

// ServerNode 服务器节点
type ServerNode struct {
	ID             int64      `json:"id" gorm:"primaryKey;autoIncrement"`
	ServerID       string     `json:"server_id" gorm:"size:64;not null;uniqueIndex"`
	LastActiveTime *time.Time `json:"last_active_time"`
	CreateTime     time.Time  `json:"create_time" gorm:"default:CURRENT_TIMESTAMP"`
	IP             string     `json:"ip" gorm:"size:512;not null;default:''"`
	Port           int        `json:"port" gorm:"not null"`
	Enable         bool       `json:"enable" gorm:"not null;default:true"`
	LocalIP        string     `json:"local_ip" gorm:"size:512"`
	OutIP          string     `json:"out_ip" gorm:"size:512"`
}

func (ServerNode) TableName() string {
	return "server_node"
}

// GroupConfig 分组配置
type GroupConfig struct {
	ID                int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	GroupName         string    `json:"group_name" gorm:"size:64;not null"`
	UserName          string    `json:"user_name" gorm:"size:64"`
	QuotaQpsGroup     float64   `json:"quota_qps_group" gorm:"not null;default:100"`
	QuotaQpsPerDevice float64   `json:"quota_qps_per_device" gorm:"not null;default:-1"`
	AllowedIPs        string    `json:"allowed_ips" gorm:"column:allowed_ips;type:text"`
	CreateDate        time.Time `json:"create_date" gorm:"not null;default:CURRENT_TIMESTAMP"`
}

func (GroupConfig) TableName() string {
	return "group_config"
}

// GroupAction 分组 Action
type GroupAction struct {
	ID           int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	GroupName    string    `json:"group_name" gorm:"size:64;not null"`
	ActionName   string    `json:"action_name" gorm:"size:64"`
	ActionParams string    `json:"action_params" gorm:"type:text;default:''"`
	CreateDate   time.Time `json:"create_date" gorm:"not null;default:CURRENT_TIMESTAMP"`
}

func (GroupAction) TableName() string {
	return "group_actions"
}

// GroupDevice 分组设备
type GroupDevice struct {
	ID             int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	GroupName      string    `json:"group_name" gorm:"size:64;not null"`
	DeviceID       string    `json:"device_id" gorm:"size:128"`
	RemoteIP       string    `json:"remote_ip" gorm:"size:64"`
	CreateDate     time.Time `json:"create_date" gorm:"not null;default:CURRENT_TIMESTAMP"`
	LastActiveTime time.Time `json:"last_active_time" gorm:"not null"`
}

func (GroupDevice) TableName() string {
	return "group_device"
}

// MetricTag 指标标签
type MetricTag struct {
	ID       int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	Name     string `json:"name" gorm:"size:64;not null;uniqueIndex"`
	Tag1Name string `json:"tag1_name" gorm:"size:64"`
	Tag2Name string `json:"tag2_name" gorm:"size:64"`
	Tag3Name string `json:"tag3_name" gorm:"size:64"`
	Tag4Name string `json:"tag4_name" gorm:"size:64"`
	Tag5Name string `json:"tag5_name" gorm:"size:64"`
}

func (MetricTag) TableName() string {
	return "metric_tag"
}

// MetricMinute 分钟级指标
type MetricMinute struct {
	ID         int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	Name       string    `json:"name" gorm:"size:64;not null"`
	TimeKey    string    `json:"time_key" gorm:"size:64;not null"`
	TagsMD5    string    `json:"tags_md5" gorm:"size:64;not null"`
	Tag1       string    `json:"tag1" gorm:"size:64"`
	Tag2       string    `json:"tag2" gorm:"size:64"`
	Tag3       string    `json:"tag3" gorm:"size:64"`
	Tag4       string    `json:"tag4" gorm:"size:64"`
	Tag5       string    `json:"tag5" gorm:"size:64"`
	Type       string    `json:"type" gorm:"size:16;not null"`
	Value      float64   `json:"value" gorm:"not null"`
	CreateTime time.Time `json:"create_time" gorm:"default:CURRENT_TIMESTAMP"`
}

func (MetricMinute) TableName() string {
	return "metric_minute"
}

// MetricHour 小时级指标
type MetricHour struct {
	ID         int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	Name       string    `json:"name" gorm:"size:64;not null"`
	TimeKey    string    `json:"time_key" gorm:"size:64;not null"`
	TagsMD5    string    `json:"tags_md5" gorm:"size:64;not null"`
	Tag1       string    `json:"tag1" gorm:"size:64"`
	Tag2       string    `json:"tag2" gorm:"size:64"`
	Tag3       string    `json:"tag3" gorm:"size:64"`
	Tag4       string    `json:"tag4" gorm:"size:64"`
	Tag5       string    `json:"tag5" gorm:"size:64"`
	Type       string    `json:"type" gorm:"size:16;not null"`
	Value      float64   `json:"value" gorm:"not null"`
	CreateTime time.Time `json:"create_time" gorm:"default:CURRENT_TIMESTAMP"`
}

func (MetricHour) TableName() string {
	return "metric_hour"
}

// MetricDay 天级指标
type MetricDay struct {
	ID         int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	Name       string    `json:"name" gorm:"size:64;not null"`
	TimeKey    string    `json:"time_key" gorm:"size:64;not null"`
	TagsMD5    string    `json:"tags_md5" gorm:"size:64;not null"`
	Tag1       string    `json:"tag1" gorm:"size:64"`
	Tag2       string    `json:"tag2" gorm:"size:64"`
	Tag3       string    `json:"tag3" gorm:"size:64"`
	Tag4       string    `json:"tag4" gorm:"size:64"`
	Tag5       string    `json:"tag5" gorm:"size:64"`
	Type       string    `json:"type" gorm:"size:16;not null"`
	Value      float64   `json:"value" gorm:"not null"`
	CreateTime time.Time `json:"create_time" gorm:"default:CURRENT_TIMESTAMP"`
}

func (MetricDay) TableName() string {
	return "metric_day"
}
