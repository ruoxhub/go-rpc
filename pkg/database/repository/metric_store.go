package repository

import (
	"fmt"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/gorm"
)

type metricStore struct {
	db *gorm.DB
}

// NewMetricStore creates a new MetricStore backed by GORM.
func NewMetricStore(db *gorm.DB) MetricStore {
	return &metricStore{db: mustDB(db)}
}

func (s *metricStore) FlushMinutes(records []model.MetricMinute) error {
	if len(records) == 0 {
		return nil
	}
	if err := s.db.CreateInBatches(records, 100).Error; err != nil {
		return fmt.Errorf("failed to flush metric minutes: %w", err)
	}
	return nil
}

func (s *metricStore) UpsertMetricTag(name, tag1, tag2, tag3 string) error {
	if err := s.db.Exec(`
		INSERT INTO metric_tag (name, tag1_name, tag2_name, tag3_name)
		VALUES (?, ?, ?, ?)
		ON CONFLICT (name) DO NOTHING
	`, name, tag1, tag2, tag3).Error; err != nil {
		return fmt.Errorf("failed to upsert metric tag: %w", err)
	}
	return nil
}

func (s *metricStore) RollupHours(hourPrefix string) error {
	query := `
		INSERT INTO metric_hour (name, time_key, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
		SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, SUM(value), MIN(create_time)
		FROM metric_minute
		WHERE time_key LIKE ? AND type = 'counter'
		GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
		ON CONFLICT (name, tags_md5, time_key)
		DO UPDATE SET value = EXCLUDED.value
	`
	if err := s.db.Exec(query, hourPrefix, hourPrefix+"%").Error; err != nil {
		return fmt.Errorf("failed to rollup counter hours: %w", err)
	}

	query = `
		INSERT INTO metric_hour (name, time_key, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
		SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, AVG(value), MIN(create_time)
		FROM metric_minute
		WHERE time_key LIKE ? AND (type = 'gauge' OR type = 'latency')
		GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
		ON CONFLICT (name, tags_md5, time_key)
		DO UPDATE SET value = EXCLUDED.value
	`
	if err := s.db.Exec(query, hourPrefix, hourPrefix+"%").Error; err != nil {
		return fmt.Errorf("failed to rollup gauge/latency hours: %w", err)
	}
	return nil
}

func (s *metricStore) RollupDays(dayPrefix string) error {
	query := `
		INSERT INTO metric_day (name, time_key, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
		SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, SUM(value), MIN(create_time)
		FROM metric_hour
		WHERE time_key LIKE ? AND type = 'counter'
		GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
		ON CONFLICT (name, tags_md5, time_key)
		DO UPDATE SET value = EXCLUDED.value
	`
	if err := s.db.Exec(query, dayPrefix, dayPrefix+"%").Error; err != nil {
		return fmt.Errorf("failed to rollup counter days: %w", err)
	}

	query = `
		INSERT INTO metric_day (name, time_key, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
		SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, AVG(value), MIN(create_time)
		FROM metric_hour
		WHERE time_key LIKE ? AND (type = 'gauge' OR type = 'latency')
		GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
		ON CONFLICT (name, tags_md5, time_key)
		DO UPDATE SET value = EXCLUDED.value
	`
	if err := s.db.Exec(query, dayPrefix, dayPrefix+"%").Error; err != nil {
		return fmt.Errorf("failed to rollup gauge/latency days: %w", err)
	}
	return nil
}

func (s *metricStore) DeleteExpired(table string, before time.Time) error {
	// Fixed SQL per table — never interpolate identifiers from callers.
	var query string
	switch table {
	case "metric_minute":
		query = `DELETE FROM metric_minute WHERE create_time < ?`
	case "metric_hour":
		query = `DELETE FROM metric_hour WHERE create_time < ?`
	case "metric_day":
		query = `DELETE FROM metric_day WHERE create_time < ?`
	default:
		return fmt.Errorf("refusing to delete from unlisted metric table %q", table)
	}
	if err := s.db.Exec(query, before).Error; err != nil {
		return fmt.Errorf("failed to delete expired metrics from %s: %w", table, err)
	}
	return nil
}

// applyMetricTagFilter appends a WHERE clause for a fixed physical tag column.
// column must be one of the five literal slots; anything else is ignored.
func applyMetricTagFilter(query *gorm.DB, column, value string) *gorm.DB {
	switch column {
	case "tag1":
		return query.Where("tag1 = ?", value)
	case "tag2":
		return query.Where("tag2 = ?", value)
	case "tag3":
		return query.Where("tag3 = ?", value)
	case "tag4":
		return query.Where("tag4 = ?", value)
	case "tag5":
		return query.Where("tag5 = ?", value)
	default:
		return query
	}
}

func (s *metricStore) QueryMetricMinutes(name string, tags map[string]string, tagMapping *MetricTagMapping, limit int) ([]MetricMinutePoint, error) {
	query := s.db.Table("metric_minute").
		Select("time_key, value").
		Where("name = ?", name).
		Order("time_key DESC").
		Limit(limit)

	if tagMapping != nil {
		// Logical tag name → fixed physical column (literal only, never free-form).
		tagColumns := map[string]string{}
		if tagMapping.Tag1Name != "" {
			tagColumns[tagMapping.Tag1Name] = "tag1"
		}
		if tagMapping.Tag2Name != "" {
			tagColumns[tagMapping.Tag2Name] = "tag2"
		}
		if tagMapping.Tag3Name != "" {
			tagColumns[tagMapping.Tag3Name] = "tag3"
		}
		if tagMapping.Tag4Name != "" {
			tagColumns[tagMapping.Tag4Name] = "tag4"
		}
		if tagMapping.Tag5Name != "" {
			tagColumns[tagMapping.Tag5Name] = "tag5"
		}
		for tagName, tagValue := range tags {
			column, ok := tagColumns[tagName]
			if !ok {
				continue
			}
			query = applyMetricTagFilter(query, column, tagValue)
		}
	} else {
		if group, ok := tags["group"]; ok {
			query = query.Where("tag1 = ?", group)
		}
		if api, ok := tags["api"]; ok {
			query = query.Where("tag2 = ?", api)
		}
	}

	var results []MetricMinutePoint
	if err := query.Scan(&results).Error; err != nil {
		return nil, fmt.Errorf("failed to query metric minutes: %w", err)
	}
	return results, nil
}

func (s *metricStore) LoadMetricTagMapping(name string) (*MetricTagMapping, error) {
	var mapping MetricTagMapping
	err := s.db.Table("metric_tag").
		Select("tag1_name, tag2_name, tag3_name, tag4_name, tag5_name").
		Where("name = ?", name).
		Scan(&mapping).Error
	if err != nil {
		return nil, err
	}
	if mapping.Tag1Name == "" {
		return nil, nil
	}
	return &mapping, nil
}
