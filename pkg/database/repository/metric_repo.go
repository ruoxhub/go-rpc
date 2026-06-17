package repository

import (
	"fmt"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/gorm"
)

type metricRepository struct {
	db *gorm.DB
}

// NewMetricRepository creates a new MetricRepository backed by GORM.
func NewMetricRepository(db *gorm.DB) MetricRepository {
	return &metricRepository{db: mustDB(db)}
}

func (r *metricRepository) FindMetrics(table, name, startTime, endTime string, limit int) ([]model.MetricMinute, error) {
	query := r.db.Table(table)
	if name != "" {
		query = query.Where("name = ?", name)
	}
	if startTime != "" {
		query = query.Where("time_key >= ?", startTime)
	}
	if endTime != "" {
		query = query.Where("time_key <= ?", endTime)
	}
	if limit <= 0 {
		limit = 100
	}

	var metrics []model.MetricMinute
	if err := query.Order("time_key DESC").Limit(limit).Find(&metrics).Error; err != nil {
		return nil, fmt.Errorf("failed to query metrics: %w", err)
	}
	return metrics, nil
}

func (r *metricRepository) FindMetricTags() ([]model.MetricTag, error) {
	var tags []model.MetricTag
	if err := r.db.Find(&tags).Error; err != nil {
		return nil, fmt.Errorf("failed to list metric tags: %w", err)
	}
	return tags, nil
}

func (r *metricRepository) GetDashboardData() (*DashboardData, error) {
	data := &DashboardData{}

	r.db.Table("metric_minute").Select("SUM(value)").Where("type = ?", "counter").Scan(&data.TotalCalls)
	r.db.Table("group_device").Where("last_active_time > ?", time.Now().Add(-5*time.Minute)).Count(&data.OnlineDevices)
	r.db.Table("group_config").Count(&data.TotalGroups)
	r.db.Table("user_info").Count(&data.TotalUsers)

	return data, nil
}

func (r *metricRepository) GetLatencyPercentiles(group, api, startTime, endTime string) ([]model.MetricMinute, error) {
	query := r.db.Table("metric_minute").Where("type = ?", "latency")

	if group != "" {
		query = query.Where("tag1 = ?", group)
	}
	if api != "" {
		query = query.Where("tag2 = ?", api)
	}
	if startTime != "" {
		query = query.Where("time_key >= ?", startTime)
	}
	if endTime != "" {
		query = query.Where("time_key <= ?", endTime)
	}

	var metrics []model.MetricMinute
	if err := query.Where("name LIKE ? OR name LIKE ? OR name LIKE ?", "%.p%", "%_p%", "%.latency").Find(&metrics).Error; err != nil {
		return nil, fmt.Errorf("failed to query latency percentiles: %w", err)
	}
	return metrics, nil
}
