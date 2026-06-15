package database

import (
	"fmt"
	"log"

	"github.com/mrh30000/go-rpc/pkg/model"
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

// AutoMigrate 检查数据库表是否存在，用于启动时的 schema 校验
func AutoMigrate() error {
	if DB == nil {
		return fmt.Errorf("database not initialized")
	}

	if !DB.Migrator().HasTable(&model.UserInfo{}) {
		log.Println("WARNING: Database schema is not initialized. Please run migration.sql first!")
		return fmt.Errorf("database schema not ready: user_info table not found")
	}

	if err := DB.AutoMigrate(&model.GroupConfig{}); err != nil {
		return fmt.Errorf("failed to auto-migrate group_config: %w", err)
	}
	if err := DB.AutoMigrate(&model.GroupAction{}); err != nil {
		return fmt.Errorf("failed to auto-migrate group_actions: %w", err)
	}

	log.Println("Database schema validation passed")
	return nil
}
