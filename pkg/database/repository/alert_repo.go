package repository

import (
	"errors"
	"fmt"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/gorm"
)

type alertRepository struct {
	db *gorm.DB
}

// NewAlertRepository creates a new AlertRepository backed by GORM.
func NewAlertRepository(db *gorm.DB) AlertRepository {
	return &alertRepository{db: mustDB(db)}
}

// Rules

func (r *alertRepository) FindRuleByID(id int64) (*model.AlertRule, error) {
	var rule model.AlertRule
	if err := r.db.First(&rule, id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to find alert rule: %w", err)
	}
	return &rule, nil
}

func (r *alertRepository) FindRulesByQuery(query model.AlertRuleQuery) ([]model.AlertRule, int64, error) {
	db := r.db.Table("alert_rule")

	if query.Group != "" {
		db = db.Where(`"group" = ?`, query.Group)
	}
	if query.Enabled != nil {
		db = db.Where("enabled = ?", *query.Enabled)
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

	var rules []model.AlertRule
	if err := db.Offset(offset).Limit(query.PageSize).Order("created_at DESC").Find(&rules).Error; err != nil {
		return nil, 0, fmt.Errorf("failed to query alert rules: %w", err)
	}
	return rules, total, nil
}

func (r *alertRepository) FindAllEnabledRules() ([]model.AlertRule, error) {
	var rules []model.AlertRule
	if err := r.db.Where("enabled = ?", true).Find(&rules).Error; err != nil {
		return nil, fmt.Errorf("failed to find enabled alert rules: %w", err)
	}
	return rules, nil
}

func (r *alertRepository) CreateRule(rule *model.AlertRule) error {
	if err := r.db.Create(rule).Error; err != nil {
		return fmt.Errorf("failed to create alert rule: %w", err)
	}
	return nil
}

func (r *alertRepository) UpdateRule(rule *model.AlertRule) error {
	if err := r.db.Save(rule).Error; err != nil {
		return fmt.Errorf("failed to update alert rule: %w", err)
	}
	return nil
}

func (r *alertRepository) DeleteRule(id int64) error {
	var rule model.AlertRule
	if err := r.db.First(&rule, id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return fmt.Errorf("alert rule not found: %w", err)
		}
		return fmt.Errorf("failed to find alert rule: %w", err)
	}
	if err := r.db.Delete(&rule).Error; err != nil {
		return fmt.Errorf("failed to delete alert rule: %w", err)
	}
	return nil
}

// History

func (r *alertRepository) FindHistoryByQuery(query model.AlertHistoryQuery) ([]model.AlertHistory, int64, error) {
	db := r.db.Table("alert_history")

	if query.RuleID > 0 {
		db = db.Where("rule_id = ?", query.RuleID)
	}
	if query.Group != "" {
		db = db.Where(`"group" = ?`, query.Group)
	}
	if query.Level != "" {
		db = db.Where("level = ?", query.Level)
	}
	if query.StartTime != "" {
		db = db.Where("triggered_at >= ?", query.StartTime)
	}
	if query.EndTime != "" {
		db = db.Where("triggered_at <= ?", query.EndTime)
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

	var histories []model.AlertHistory
	if err := db.Offset(offset).Limit(query.PageSize).Order("triggered_at DESC").Find(&histories).Error; err != nil {
		return nil, 0, fmt.Errorf("failed to query alert history: %w", err)
	}
	return histories, total, nil
}

func (r *alertRepository) CreateHistory(history *model.AlertHistory) error {
	if err := r.db.Create(history).Error; err != nil {
		return fmt.Errorf("failed to create alert history: %w", err)
	}
	return nil
}

func (r *alertRepository) CountRecentHistory(ruleID int64, since time.Time) (int64, error) {
	var count int64
	if err := r.db.Table("alert_history").
		Where("rule_id = ? AND triggered_at > ?", ruleID, since).
		Count(&count).Error; err != nil {
		return 0, fmt.Errorf("failed to count recent alert history: %w", err)
	}
	return count, nil
}
