package repository

import (
	"fmt"

	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/gorm"
)

type sysConfigRepository struct {
	db *gorm.DB
}

// NewSysConfigRepository creates a new SysConfigRepository backed by GORM.
func NewSysConfigRepository(db *gorm.DB) SysConfigRepository {
	return &sysConfigRepository{db: mustDB(db)}
}

func (r *sysConfigRepository) FindAll() ([]model.SysConfig, error) {
	var configs []model.SysConfig
	if err := r.db.Find(&configs).Error; err != nil {
		return nil, fmt.Errorf("failed to list sys configs: %w", err)
	}
	return configs, nil
}

func (r *sysConfigRepository) FindByKey(key string) (*model.SysConfig, error) {
	var config model.SysConfig
	if err := r.db.Where("config_key = ?", key).First(&config).Error; err != nil {
		return nil, fmt.Errorf("failed to find sys config: %w", err)
	}
	return &config, nil
}

func (r *sysConfigRepository) Upsert(key, value string) error {
	if err := r.db.Model(&model.SysConfig{}).
		Where("config_key = ?", key).
		Update("config_value", value).Error; err != nil {
		return fmt.Errorf("failed to update sys config: %w", err)
	}
	return nil
}

// serverNodeRepository

type serverNodeRepository struct {
	db *gorm.DB
}

// NewServerNodeRepository creates a new ServerNodeRepository backed by GORM.
func NewServerNodeRepository(db *gorm.DB) ServerNodeRepository {
	return &serverNodeRepository{db: mustDB(db)}
}

func (r *serverNodeRepository) FindAll() ([]model.ServerNode, error) {
	var nodes []model.ServerNode
	if err := r.db.Find(&nodes).Error; err != nil {
		return nil, fmt.Errorf("failed to list server nodes: %w", err)
	}
	return nodes, nil
}

// sysLogRepository

type sysLogRepository struct {
	db *gorm.DB
}

// NewSysLogRepository creates a new SysLogRepository backed by GORM.
func NewSysLogRepository(db *gorm.DB) SysLogRepository {
	return &sysLogRepository{db: mustDB(db)}
}

func (r *sysLogRepository) Create(log *model.SysLog) error {
	if err := r.db.Create(log).Error; err != nil {
		return fmt.Errorf("failed to create sys log: %w", err)
	}
	return nil
}

func (r *sysLogRepository) FindAll(query SysLogQuery) ([]model.SysLog, int64, error) {
	db := r.db.Table("sys_log")

	if query.Level != "" {
		db = db.Where("level = ?", query.Level)
	}
	if query.StartTime != "" {
		db = db.Where("create_time >= ?", query.StartTime)
	}
	if query.EndTime != "" {
		db = db.Where("create_time <= ?", query.EndTime)
	}
	if query.Keyword != "" {
		db = db.Where("message LIKE ? OR detail LIKE ?", "%"+query.Keyword+"%", "%"+query.Keyword+"%")
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

	var logs []model.SysLog
	if err := db.Offset(offset).Limit(query.PageSize).Order("create_time DESC").Find(&logs).Error; err != nil {
		return nil, 0, fmt.Errorf("failed to list sys logs: %w", err)
	}
	return logs, total, nil
}
