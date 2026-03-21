package model

import "time"

// TraceRecord 调用链路追踪记录
type TraceRecord struct {
	ID           int64     `json:"id" gorm:"primaryKey;autoIncrement"`
	TraceID      string    `json:"trace_id" gorm:"size:64;not null;index"`
	SpanID       string    `json:"span_id" gorm:"size:64;not null"`
	ParentSpanID string    `json:"parent_span_id" gorm:"size:64"`
	Group        string    `json:"group" gorm:"size:64;index"`
	DeviceID     string    `json:"device_id" gorm:"size:128"`
	API          string    `json:"api" gorm:"size:256"`
	Caller       string    `json:"caller" gorm:"size:128"`
	StartTime    time.Time `json:"start_time" gorm:"not null;index"`
	EndTime      time.Time `json:"end_time" gorm:"not null"`
	DurationMs   int64     `json:"duration_ms" gorm:"not null"`
	Status       string    `json:"status" gorm:"size:16;not null"` // SUCCESS, FAILURE
	ErrorMessage string    `json:"error_message" gorm:"type:text"`
	ExtraData    string    `json:"extra_data" gorm:"type:text"` // JSON 格式额外数据
}

func (TraceRecord) TableName() string {
	return "trace_record"
}

// TraceQuery 追踪查询参数
type TraceQuery struct {
	TraceID     string `json:"traceId" form:"traceId"`
	Group       string `json:"group" form:"group"`
	DeviceID    string `json:"deviceId" form:"deviceId"`
	API         string `json:"api" form:"api"`
	Status      string `json:"status" form:"status"`
	StartTime   string `json:"startTime" form:"startTime"`
	EndTime     string `json:"endTime" form:"endTime"`
	MinDuration int64  `json:"minDuration" form:"minDuration"`
	MaxDuration int64  `json:"maxDuration" form:"maxDuration"`
	Page        int    `json:"page" form:"page" form:"1"`
	PageSize    int    `json:"pageSize" form:"pageSize" form:"20"`
}

// SpanStatus 追踪状态常量
const (
	SpanStatusSuccess = "SUCCESS"
	SpanStatusFailure = "FAILURE"
)
