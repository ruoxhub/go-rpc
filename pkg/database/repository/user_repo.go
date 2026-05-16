package repository

import (
	"errors"
	"fmt"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/gorm"
)

type userRepository struct {
	db *gorm.DB
}

// NewUserRepository creates a new UserRepository backed by GORM.
func NewUserRepository(db *gorm.DB) UserRepository {
	return &userRepository{db: db}
}

func (r *userRepository) getDB() *gorm.DB {
	if r.db != nil {
		return r.db
	}
	return GetDB()
}

func (r *userRepository) FindByID(id int64) (*model.UserInfo, error) {
	var user model.UserInfo
	if err := r.getDB().First(&user, id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, fmt.Errorf("user not found: %w", err)
		}
		return nil, fmt.Errorf("failed to find user: %w", err)
	}
	return &user, nil
}

func (r *userRepository) FindByUserName(name string) (*model.UserInfo, error) {
	var user model.UserInfo
	if err := r.getDB().Where("user_name = ?", name).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to find user by name: %w", err)
	}
	return &user, nil
}

func (r *userRepository) FindByToken(token string) (*model.UserInfo, error) {
	if token == "" {
		return nil, fmt.Errorf("empty token")
	}
	var user model.UserInfo
	if err := r.getDB().Where("api_token = ?", token).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to find user by token: %w", err)
	}
	return &user, nil
}

func (r *userRepository) Create(user *model.UserInfo) error {
	if err := r.getDB().Create(user).Error; err != nil {
		return fmt.Errorf("failed to create user: %w", err)
	}
	return nil
}

func (r *userRepository) Update(user *model.UserInfo) error {
	if err := r.getDB().Save(user).Error; err != nil {
		return fmt.Errorf("failed to update user: %w", err)
	}
	return nil
}

func (r *userRepository) UpdateFields(id int64, fields map[string]interface{}) error {
	fields["update_time"] = time.Now()
	if err := r.getDB().Model(&model.UserInfo{}).Where("id = ?", id).Updates(fields).Error; err != nil {
		return fmt.Errorf("failed to update user fields: %w", err)
	}
	return nil
}

func (r *userRepository) Delete(id int64) error {
	if err := r.getDB().Delete(&model.UserInfo{}, id).Error; err != nil {
		return fmt.Errorf("failed to delete user: %w", err)
	}
	return nil
}

func (r *userRepository) List(order string) ([]model.UserInfo, error) {
	var users []model.UserInfo
	if err := r.getDB().Order(order).Find(&users).Error; err != nil {
		return nil, fmt.Errorf("failed to list users: %w", err)
	}
	return users, nil
}

func (r *userRepository) CountByUserName(name string) (int64, error) {
	var count int64
	if err := r.getDB().Model(&model.UserInfo{}).
		Where("user_name = ?", name).
		Count(&count).Error; err != nil {
		return 0, fmt.Errorf("failed to count user: %w", err)
	}
	return count, nil
}
