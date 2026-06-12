package repository

import (
	"fmt"

	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/gorm"
)

type traceRepository struct {
	db *gorm.DB
}

// NewTraceRepository creates a new TraceRepository backed by GORM.
func NewTraceRepository(db *gorm.DB) TraceRepository {
	return &traceRepository{db: db}
}

func (r *traceRepository) getDB() *gorm.DB {
	if r.db != nil {
		return r.db
	}
	return GetDB()
}

func (r *traceRepository) FindByQuery(query model.TraceQuery) ([]model.TraceRecord, int64, error) {
	db := r.getDB().Table("trace_record")

	if query.TraceID != "" {
		db = db.Where("trace_id = ?", query.TraceID)
	}
	if query.Group != "" {
		db = db.Where(`"group" = ?`, query.Group)
	}
	if query.DeviceID != "" {
		db = db.Where("device_id = ?", query.DeviceID)
	}
	if query.API != "" {
		db = db.Where("api LIKE ?", "%"+query.API+"%")
	}
	if query.Status != "" {
		db = db.Where("status = ?", query.Status)
	}
	if query.StartTime != "" {
		db = db.Where("start_time >= ?", query.StartTime)
	}
	if query.EndTime != "" {
		db = db.Where("end_time <= ?", query.EndTime)
	}
	if query.MinDuration > 0 {
		db = db.Where("duration_ms >= ?", query.MinDuration)
	}
	if query.MaxDuration > 0 {
		db = db.Where("duration_ms <= ?", query.MaxDuration)
	}

	var total int64
	db.Count(&total)

	if query.Page <= 0 {
		query.Page = 1
	}
	if query.PageSize <= 0 {
		query.PageSize = 20
	}
	offset := (query.Page - 1) * query.PageSize

	var records []model.TraceRecord
	if err := db.Offset(offset).Limit(query.PageSize).Order("start_time DESC").Find(&records).Error; err != nil {
		return nil, 0, fmt.Errorf("failed to query traces: %w", err)
	}
	return records, total, nil
}

func (r *traceRepository) FindByTraceID(traceID string) ([]model.TraceRecord, error) {
	var records []model.TraceRecord
	if err := r.getDB().Where("trace_id = ?", traceID).Order("start_time ASC").Find(&records).Error; err != nil {
		return nil, fmt.Errorf("failed to find traces by traceID: %w", err)
	}
	return records, nil
}

func (r *traceRepository) FindFirstByTraceID(traceID string) (*model.TraceRecord, error) {
	var record model.TraceRecord
	if err := r.getDB().Where("trace_id = ?", traceID).First(&record).Error; err != nil {
		return nil, fmt.Errorf("failed to find trace record: %w", err)
	}
	return &record, nil
}

func (r *traceRepository) GetStats(group, api, startTime, endTime string) (*TraceStats, error) {
	query := r.getDB().Table("trace_record")

	if group != "" {
		query = query.Where(`"group" = ?`, group)
	}
	if api != "" {
		query = query.Where("api LIKE ?", "%"+api+"%")
	}
	if startTime != "" {
		query = query.Where("start_time >= ?", startTime)
	}
	if endTime != "" {
		query = query.Where("start_time <= ?", endTime)
	}

	var total, successCount, failureCount int64
	var avgLatency float64
	var maxLatency, minLatency int64

	baseQuery := r.getDB().Table("trace_record")
	if group != "" {
		baseQuery = baseQuery.Where(`"group" = ?`, group)
	}
	if api != "" {
		baseQuery = baseQuery.Where("api LIKE ?", "%"+api+"%")
	}
	if startTime != "" {
		baseQuery = baseQuery.Where("start_time >= ?", startTime)
	}
	if endTime != "" {
		baseQuery = baseQuery.Where("start_time <= ?", endTime)
	}

	baseQuery.Count(&total)
	baseQuery.Where("status = ?", model.SpanStatusSuccess).Count(&successCount)
	baseQuery.Where("status = ?", model.SpanStatusFailure).Count(&failureCount)
	baseQuery.Select("AVG(duration_ms)").Scan(&avgLatency)
	baseQuery.Select("MAX(duration_ms)").Scan(&maxLatency)
	baseQuery.Select("MIN(duration_ms)").Scan(&minLatency)

	successRate := 0.0
	if total > 0 {
		successRate = float64(successCount) / float64(total) * 100
	}

	return &TraceStats{
		Total:        total,
		SuccessCount: successCount,
		FailureCount: failureCount,
		SuccessRate:  successRate,
		AvgLatency:   avgLatency,
		MaxLatency:   maxLatency,
		MinLatency:   minLatency,
	}, nil
}

func (r *traceRepository) GetTimeline(group, api string, limit int) ([]model.TraceRecord, error) {
	query := r.getDB().Table("trace_record")

	if group != "" {
		query = query.Where(`"group" = ?`, group)
	}
	if api != "" {
		query = query.Where("api LIKE ?", "%"+api+"%")
	}

	if limit <= 0 {
		limit = 100
	}

	var records []model.TraceRecord
	query.Order("start_time DESC").Limit(limit).Find(&records)
	return records, nil
}

func (r *traceRepository) Create(record *model.TraceRecord) error {
	if err := r.getDB().Create(record).Error; err != nil {
		return fmt.Errorf("failed to create trace record: %w", err)
	}
	return nil
}
