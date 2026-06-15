package repository

import (
	"errors"
	"fmt"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

type groupRepository struct {
	db *gorm.DB
}

// NewGroupRepository creates a new GroupRepository backed by GORM.
func NewGroupRepository(db *gorm.DB) GroupRepository {
	return &groupRepository{db: db}
}

func (r *groupRepository) getDB() *gorm.DB {
	if r.db != nil {
		return r.db
	}
	return GetDB()
}

// Group operations

func (r *groupRepository) FindGroupByName(name string) (*model.GroupConfig, error) {
	var group model.GroupConfig
	if err := r.getDB().Where("group_name = ?", name).First(&group).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to find group: %w", err)
	}
	return &group, nil
}

func (r *groupRepository) FindAllGroups() ([]model.GroupConfig, error) {
	var groups []model.GroupConfig
	if err := r.getDB().Find(&groups).Error; err != nil {
		return nil, fmt.Errorf("failed to list groups: %w", err)
	}
	return groups, nil
}

func (r *groupRepository) CreateGroup(group *model.GroupConfig) error {
	if err := r.getDB().Create(group).Error; err != nil {
		return fmt.Errorf("failed to create group: %w", err)
	}
	return nil
}

func (r *groupRepository) UpdateGroup(name string, updates map[string]interface{}) error {
	if err := r.getDB().Model(&model.GroupConfig{}).
		Where("group_name = ?", name).
		Updates(updates).Error; err != nil {
		return fmt.Errorf("failed to update group: %w", err)
	}
	return nil
}

func (r *groupRepository) DeleteGroup(name string) error {
	if err := r.getDB().Where("group_name = ?", name).Delete(&model.GroupConfig{}).Error; err != nil {
		return fmt.Errorf("failed to delete group: %w", err)
	}
	return nil
}

func (r *groupRepository) CountGroups() (int64, error) {
	var count int64
	if err := r.getDB().Table("group_config").Count(&count).Error; err != nil {
		return 0, fmt.Errorf("failed to count groups: %w", err)
	}
	return count, nil
}

// Group statistics

func (r *groupRepository) GetGroupStats(userName string, isAdmin bool, activeThreshold string) ([]GroupStats, error) {
	db := r.getDB()

	type rawStat struct {
		ID                int64
		GroupName         string
		UserName          string
		QuotaQpsGroup     float64
		QuotaQpsPerDevice float64
		AllowedIPs        string
		CreateDate        time.Time
		AvailableClients  int64
		DisabledClients   int64
	}

	query := db.Table("group_config gc").
		Select(`
			gc.id, gc.group_name, gc.user_name,
			gc.quota_qps_group, gc.quota_qps_per_device, gc.allowed_ips, gc.create_date,
			COUNT(gd.id) as total_clients,
			SUM(CASE WHEN gd.last_active_time > ? THEN 1 ELSE 0 END) as available_clients,
			SUM(CASE WHEN gd.last_active_time <= ? THEN 1 ELSE 0 END) as disabled_clients
		`, activeThreshold, activeThreshold).
		Joins("LEFT JOIN group_device gd ON gc.group_name = gd.group_name").
		Group("gc.id, gc.group_name, gc.user_name, gc.quota_qps_group, gc.quota_qps_per_device, gc.allowed_ips, gc.create_date").
		Order("gc.create_date DESC")

	if !isAdmin {
		query = query.Where("gc.user_name = ?", userName)
	}

	var rawStats []rawStat
	if err := query.Scan(&rawStats).Error; err != nil {
		return nil, fmt.Errorf("failed to get group stats: %w", err)
	}

	stats := make([]GroupStats, len(rawStats))
	for i, s := range rawStats {
		stats[i] = GroupStats{
			ID:                s.ID,
			GroupName:         s.GroupName,
			UserName:          s.UserName,
			QuotaQpsGroup:     s.QuotaQpsGroup,
			QuotaQpsPerDevice: s.QuotaQpsPerDevice,
			AllowedIPs:        s.AllowedIPs,
			CreateDate:        s.CreateDate.Format("2006-01-02 15:04:05"),
			AvailableClients:  s.AvailableClients,
			DisabledClients:   s.DisabledClients,
		}
	}
	return stats, nil
}

type groupDeviceStats struct {
	Available int64
	Disabled  int64
}

func (r *groupRepository) GetGroupDeviceStats(name string, activeThreshold string) (available, disabled int64, err error) {
	var stats groupDeviceStats
	err = r.getDB().Model(&model.GroupDevice{}).
		Select(`
			SUM(CASE WHEN last_active_time > ? THEN 1 ELSE 0 END) as available,
			SUM(CASE WHEN last_active_time <= ? THEN 1 ELSE 0 END) as disabled
		`, activeThreshold, activeThreshold).
		Where("group_name = ?", name).
		Scan(&stats).Error
	if err != nil {
		return 0, 0, fmt.Errorf("failed to get group device stats: %w", err)
	}
	return stats.Available, stats.Disabled, nil
}

// Device operations

func (r *groupRepository) FindDevicesByGroup(name string) ([]model.GroupDevice, error) {
	var devices []model.GroupDevice
	if err := r.getDB().Where("group_name = ?", name).Find(&devices).Error; err != nil {
		return nil, fmt.Errorf("failed to list devices: %w", err)
	}
	return devices, nil
}

func (r *groupRepository) FindDevice(groupName, deviceID string) (*model.GroupDevice, error) {
	var device model.GroupDevice
	if err := r.getDB().Where("group_name = ? AND device_id = ?", groupName, deviceID).First(&device).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to find device: %w", err)
	}
	return &device, nil
}

func (r *groupRepository) CreateDevice(device *model.GroupDevice) error {
	if err := r.getDB().Create(device).Error; err != nil {
		return fmt.Errorf("failed to create device: %w", err)
	}
	return nil
}

func (r *groupRepository) UpdateDevice(groupName, deviceID string, updates map[string]interface{}) error {
	if err := r.getDB().Model(&model.GroupDevice{}).
		Where("group_name = ? AND device_id = ?", groupName, deviceID).
		Updates(updates).Error; err != nil {
		return fmt.Errorf("failed to update device: %w", err)
	}
	return nil
}

func (r *groupRepository) DeleteDevice(groupName, deviceID string) error {
	if err := r.getDB().Where("group_name = ? AND device_id = ?", groupName, deviceID).
		Delete(&model.GroupDevice{}).Error; err != nil {
		return fmt.Errorf("failed to delete device: %w", err)
	}
	return nil
}

func (r *groupRepository) DeleteDevicesByGroup(name string) error {
	if err := r.getDB().Where("group_name = ?", name).Delete(&model.GroupDevice{}).Error; err != nil {
		return fmt.Errorf("failed to delete devices by group: %w", err)
	}
	return nil
}

func (r *groupRepository) CountOnlineDevices(since string) (int64, error) {
	var count int64
	if err := r.getDB().Table("group_device").
		Where("last_active_time > ?", since).
		Count(&count).Error; err != nil {
		return 0, fmt.Errorf("failed to count online devices: %w", err)
	}
	return count, nil
}

func (r *groupRepository) CountDevicesByGroup(name string) (int64, error) {
	var count int64
	if err := r.getDB().Table("group_device").
		Where("group_name = ?", name).
		Count(&count).Error; err != nil {
		return 0, fmt.Errorf("failed to count devices: %w", err)
	}
	return count, nil
}

// Action operations

func (r *groupRepository) FindActionsByGroup(name string) ([]model.GroupAction, error) {
	var actions []model.GroupAction
	if err := r.getDB().Where("group_name = ?", name).Find(&actions).Error; err != nil {
		return nil, fmt.Errorf("failed to list actions: %w", err)
	}
	return actions, nil
}

func (r *groupRepository) FindAction(groupName, actionName string) (*model.GroupAction, error) {
	var action model.GroupAction
	if err := r.getDB().Where("group_name = ? AND action_name = ?", groupName, actionName).First(&action).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to find action: %w", err)
	}
	return &action, nil
}

func (r *groupRepository) CreateAction(action *model.GroupAction) error {
	if err := r.getDB().Create(action).Error; err != nil {
		return fmt.Errorf("failed to create action: %w", err)
	}
	return nil
}

func (r *groupRepository) UpsertAction(action *model.GroupAction) error {
	assignments := map[string]interface{}{}
	if action.ActionParams != "" {
		assignments["action_params"] = action.ActionParams
	}
	if len(assignments) == 0 {
		return r.CreateAction(action)
	}

	if err := r.getDB().Clauses(clause.OnConflict{
		Columns:   []clause.Column{{Name: "group_name"}, {Name: "action_name"}},
		DoUpdates: clause.Assignments(assignments),
	}).Create(action).Error; err != nil {
		return fmt.Errorf("failed to upsert action: %w", err)
	}
	return nil
}

func (r *groupRepository) UpdateActionParams(groupName, actionName, actionParams string) error {
	if err := r.getDB().Model(&model.GroupAction{}).
		Where("group_name = ? AND action_name = ?", groupName, actionName).
		Update("action_params", actionParams).Error; err != nil {
		return fmt.Errorf("failed to update action params: %w", err)
	}
	return nil
}

func (r *groupRepository) DeleteAction(groupName, actionName string) error {
	if err := r.getDB().Where("group_name = ? AND action_name = ?", groupName, actionName).
		Delete(&model.GroupAction{}).Error; err != nil {
		return fmt.Errorf("failed to delete action: %w", err)
	}
	return nil
}

func (r *groupRepository) DeleteActionsByGroup(name string) error {
	if err := r.getDB().Where("group_name = ?", name).Delete(&model.GroupAction{}).Error; err != nil {
		return fmt.Errorf("failed to delete actions by group: %w", err)
	}
	return nil
}

// Anonymous group operations

func (r *groupRepository) FindAnonymousDeviceGroups(activeThreshold string) ([]AnonymousGroupStats, error) {
	type rawStat struct {
		GroupName string
		Total     int64
		Active    int64
		Disabled  int64
	}

	var rawStats []rawStat
	if err := r.getDB().Table("group_device gd").
		Select(`
			gd.group_name,
			COUNT(*) as total,
			SUM(CASE WHEN gd.last_active_time > ? THEN 1 ELSE 0 END) as active,
			SUM(CASE WHEN gd.last_active_time <= ? THEN 1 ELSE 0 END) as disabled
		`, activeThreshold, activeThreshold).
		Where("NOT EXISTS (SELECT 1 FROM group_config gc WHERE gc.group_name = gd.group_name)").
		Group("gd.group_name").
		Find(&rawStats).Error; err != nil {
		return nil, fmt.Errorf("failed to find anonymous groups: %w", err)
	}

	stats := make([]AnonymousGroupStats, len(rawStats))
	for i, s := range rawStats {
		stats[i] = AnonymousGroupStats{
			GroupName:        s.GroupName,
			TotalClients:     s.Total,
			AvailableClients: s.Active,
			DisabledClients:  s.Disabled,
		}
	}
	return stats, nil
}

func (r *groupRepository) IsAnonymousGroup(name string) (bool, error) {
	var count int64
	if err := r.getDB().Model(&model.GroupConfig{}).
		Where("group_name = ?", name).
		Count(&count).Error; err != nil {
		return false, fmt.Errorf("failed to check anonymous group: %w", err)
	}
	return count == 0, nil
}

func (r *groupRepository) DeleteAnonymousGroupDevices(name string) (int64, error) {
	result := r.getDB().Where("group_name = ?", name).Delete(&model.GroupDevice{})
	if result.Error != nil {
		return 0, fmt.Errorf("failed to delete anonymous group devices: %w", result.Error)
	}
	return result.RowsAffected, nil
}

// Convenience methods

func (r *groupRepository) IsGroupRegistered(name string) (bool, error) {
	var count int64
	if err := r.getDB().Model(&model.GroupConfig{}).
		Where("group_name = ?", name).
		Count(&count).Error; err != nil {
		return false, fmt.Errorf("failed to check group registration: %w", err)
	}
	return count > 0, nil
}

func (r *groupRepository) EnsureDefaultActions(groupName string) error {
	for _, actionName := range model.DefaultGroupActions {
		existing, err := r.FindAction(groupName, actionName)
		if err != nil {
			return fmt.Errorf("failed to check action: %w", err)
		}
		if existing != nil {
			continue
		}
		action := model.GroupAction{
			GroupName:  groupName,
			ActionName: actionName,
			CreateDate: time.Now(),
		}
		if err := r.CreateAction(&action); err != nil {
			return fmt.Errorf("failed to create default action %s: %w", actionName, err)
		}
	}
	return nil
}

func (r *groupRepository) UpsertDevice(device *model.GroupDevice) error {
	if err := r.getDB().
		Where("group_name = ? AND device_id = ?", device.GroupName, device.DeviceID).
		FirstOrCreate(device).Error; err != nil {
		return fmt.Errorf("failed to upsert device: %w", err)
	}
	return nil
}

func (r *groupRepository) UpdateDeviceLastActive(groupName, deviceID string, t time.Time) error {
	if err := r.getDB().Model(&model.GroupDevice{}).
		Where("group_name = ? AND device_id = ?", groupName, deviceID).
		Update("last_active_time", t).Error; err != nil {
		return fmt.Errorf("failed to update device last_active_time: %w", err)
	}
	return nil
}

// Transaction support

type txGroupRepository struct {
	groupRepository
}

func (r *groupRepository) WithTx(tx interface{}) GroupRepository {
	gormTx, ok := tx.(*gorm.DB)
	if !ok {
		return r
	}
	return &txGroupRepository{
		groupRepository: groupRepository{db: gormTx},
	}
}

func (r *groupRepository) BeginTx() GroupRepository {
	return &groupRepository{db: r.getDB().Begin()}
}

func (r *groupRepository) Commit() error {
	if r.db == nil {
		return fmt.Errorf("commit called on non-transaction repository")
	}
	return r.db.Commit().Error
}

func (r *groupRepository) Rollback() error {
	if r.db == nil {
		return fmt.Errorf("rollback called on non-transaction repository")
	}
	return r.db.Rollback().Error
}
