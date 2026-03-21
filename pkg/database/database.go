package database

import (
	"fmt"
	"log"
	"time"

	"github.com/google/uuid"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"github.com/sekiro-go/sekiro-go/pkg/utils/password"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var DB *gorm.DB

// Config 数据库配置
type Config struct {
	Host     string
	Port     int
	User     string
	Password string
	DBName   string
	SSLMode  string
}

// DefaultConfig 返回默认配置
func DefaultConfig() Config {
	return Config{
		Host:     "localhost",
		Port:     5432,
		User:     "postgres",
		Password: "postgres",
		DBName:   "sekiro",
		SSLMode:  "disable",
	}
}

// Init 初始化数据库连接
func Init(cfg Config) error {
	dsn := fmt.Sprintf(
		"host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
		cfg.Host, cfg.Port, cfg.User, cfg.Password, cfg.DBName, cfg.SSLMode,
	)

	var err error
	DB, err = gorm.Open(postgres.Open(dsn), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Info),
	})

	if err != nil {
		return fmt.Errorf("failed to connect to database: %w", err)
	}

	log.Println("Database connection established successfully")
	return nil
}

// InitFromConfig 从全局配置初始化数据库连接
func InitFromConfig(host string, port int, user, password, dbName, sslMode string) error {
	return Init(Config{
		Host:     host,
		Port:     port,
		User:     user,
		Password: password,
		DBName:   dbName,
		SSLMode:  sslMode,
	})
}

// GetDB 获取数据库实例
func GetDB() *gorm.DB {
	return DB
}

// AutoMigrate 自动迁移数据库表
func AutoMigrate() error {
	if DB == nil {
		return fmt.Errorf("database not initialized")
	}

	err := DB.AutoMigrate(
		&model.UserInfo{},
		&model.SysConfig{},
		&model.SysLog{},
		&model.ServerNode{},
		&model.GroupConfig{},
		&model.GroupAction{},
		&model.GroupDevice{},
		&model.MetricTag{},
		&model.MetricMinute{},
		&model.MetricHour{},
		&model.MetricDay{},
	)
	if err != nil {
		return err
	}

	// 创建默认管理员用户
	return createDefaultAdminUser()
}

// createDefaultAdminUser 创建默认管理员用户
func createDefaultAdminUser() error {
	var count int64
	DB.Model(&model.UserInfo{}).Where("user_name = ?", "admin").Count(&count)
	if count == 0 {
		now := time.Now()

		// 哈希默认密码
		hashedPassword, err := password.HashPassword("admin123")
		if err != nil {
			return err
		}

		adminUser := model.UserInfo{
			UserName:   "admin",
			Password:   hashedPassword,
			IsAdmin:    true,
			QuotaQps:   1000,
			ApiToken:   "admin-token-" + uuid.New().String(),
			LoginToken: uuid.New().String(),
			CreateTime: now,
			LastActive: now,
			UpdateTime: &now,
		}
		return DB.Create(&adminUser).Error
	}
	return nil
}
