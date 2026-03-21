package model

import (
	"time"
)

// AlertRule 告警规则
type AlertRule struct {
	ID          int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	Name        string    `json:"name" gorm:"size:128;not null;uniqueIndex"`
	Description string    `json:"description" gorm:"size:512"`
	Group       string    `json:"group" gorm:"size:64;index"` // 分组名称，空表示全局规则
	API         string    `json:"api" gorm:"size:256"`         // API 名称，空表示所有 API

	// 告警条件
	MetricName  string  `json:"metric_name" gorm:"size:128;not null"` // 指标名称，如 invoke.total, invoke.latency
	Operator    string  `json:"operator" gorm:"size:8;not null"`      // 操作符：>, <, >=, <=, ==, !=
	Threshold   float64 `json:"threshold" gorm:"not null"`            // 阈值
	Window      int     `json:"window" gorm:"not null"`               // 时间窗口（分钟）

	// 通知配置
	WebhookURL  string `json:"webhook_url" gorm:"size:512"`  // Webhook URL
	Email       string `json:"email" gorm:"size:256"`        // 通知邮箱
	Enabled     bool   `json:"enabled" gorm:"default:true"`  // 是否启用

	CreatedAt   time.Time `json:"created_at" gorm:"autoCreateTime"`
	UpdatedAt   time.Time `json:"updated_at" gorm:"autoUpdateTime"`
}

func (AlertRule) TableName() string {
	return "alert_rule"
}

// AlertHistory 告警历史
type AlertHistory struct {
	ID          int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	RuleID      int64     `json:"rule_id" gorm:"not null;index"`
	RuleName    string    `json:"rule_name" gorm:"size:128;not null"`
	Group       string    `json:"group" gorm:"size:64;index"`
	API         string    `json:"api" gorm:"size:256"`
	MetricName  string    `json:"metric_name" gorm:"size:128;not null"`

	// 触发时的值
	CurrentValue float64   `json:"current_value" gorm:"not null"`
	Threshold    float64   `json:"threshold" gorm:"not null"`
	Operator     string    `json:"operator" gorm:"size:8;not null"`

	// 告警级别
	Level        string    `json:"level" gorm:"size:16"` // INFO, WARNING, CRITICAL

	// 通知状态
	Notified     bool      `json:"notified" gorm:"default:false"`
	NotifyError  string    `json:"notify_error" gorm:"size:512"`

	TriggeredAt  time.Time `json:"triggered_at" gorm:"not null;index"`
	Message      string    `json:"message" gorm:"type:text"`
}

func (AlertHistory) TableName() string {
	return "alert_history"
}

// AlertLevel 告警级别
const (
	AlertLevelInfo      = "INFO"
	AlertLevelWarning   = "WARNING"
	AlertLevelCritical  = "CRITICAL"
)

// AlertOperator 告警操作符
const (
	OpGreaterThan         = ">"
	OpLessThan            = "<"
	OpGreaterThanOrEqual  = ">="
	OpLessThanOrEqual     = "<="
	OpEqual               = "=="
	OpNotEqual            = "!="
)

// AlertRuleQuery 告警规则查询参数
type AlertRuleQuery struct {
	Group   string `json:"group" form:"group"`
	Enabled *bool  `json:"enabled" form:"enabled"` // nil 表示全部
	Page    int    `json:"page" form:"page" form:"1"`
	PageSize int   `json:"pageSize" form:"pageSize" form:"20"`
}

// AlertHistoryQuery 告警历史查询参数
type AlertHistoryQuery struct {
	RuleID    int64  `json:"ruleId" form:"ruleId"`
	Group     string `json:"group" form:"group"`
	Level     string `json:"level" form:"level"`
	StartTime string `json:"startTime" form:"startTime"`
	EndTime   string `json:"endTime" form:"endTime"`
	Page      int    `json:"page" form:"page" form:"1"`
	PageSize  int    `json:"pageSize" form:"pageSize" form:"20"`
}
