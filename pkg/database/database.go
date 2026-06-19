package database

import (
	"fmt"
	"time"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/model"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	gormlogger "gorm.io/gorm/logger"
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
		Logger: gormlogger.Default.LogMode(gormlogger.Silent),
	})

	if err != nil {
		return fmt.Errorf("failed to connect to database: %w", err)
	}

	logger.Info("Database connection established successfully")
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

// ConfigurePool 把连接池参数应用到已建立的底层 *sql.DB。
// 应在 Init / InitFromConfig 成功后调用。
// maxOpen/maxIdle <= 0 表示保留驱动默认；maxLifetimeSeconds <= 0 表示不限制连接寿命。
func ConfigurePool(maxOpen, maxIdle, maxLifetimeSeconds int) error {
	if DB == nil {
		return fmt.Errorf("database not initialized")
	}
	sqlDB, err := DB.DB()
	if err != nil {
		return fmt.Errorf("failed to obtain underlying *sql.DB: %w", err)
	}

	if maxOpen > 0 {
		sqlDB.SetMaxOpenConns(maxOpen)
	}
	if maxIdle > 0 {
		sqlDB.SetMaxIdleConns(maxIdle)
	}
	if maxLifetimeSeconds > 0 {
		sqlDB.SetConnMaxLifetime(time.Duration(maxLifetimeSeconds) * time.Second)
	}

	logger.Infof("Database pool configured: max_open=%d max_idle=%d max_lifetime=%ds",
		maxOpen, maxIdle, maxLifetimeSeconds)
	return nil
}

// GetDB 获取数据库实例
func GetDB() *gorm.DB {
	return DB
}

// ResetMetricTables 删除全部 metric 相关表（metric_minute / metric_hour / metric_day / metric_tag）。
// 通常配合随后的 AutoMigrate 使用：AutoMigrate 会重建表结构与唯一索引。
// 仅在需要一键重建指标库时使用（例如测试环境），生产环境禁用。
func ResetMetricTables() error {
	if DB == nil {
		return fmt.Errorf("database not initialized")
	}
	tables := []string{"metric_minute", "metric_hour", "metric_day", "metric_tag"}
	for _, t := range tables {
		if err := DB.Migrator().DropTable(t); err != nil {
			return fmt.Errorf("failed to drop table %s: %w", t, err)
		}
		logger.Infof("Dropped metric table: %s", t)
	}
	return nil
}

// AutoMigrate 检查数据库表是否存在，用于启动时的 schema 校验
func AutoMigrate() error {
	if DB == nil {
		return fmt.Errorf("database not initialized")
	}

	if !DB.Migrator().HasTable(&model.UserInfo{}) {
		logger.Warnf("Database schema is not initialized. Please run migration.sql first!")
		return fmt.Errorf("database schema not ready: user_info table not found")
	}

	if err := DB.AutoMigrate(&model.GroupConfig{}); err != nil {
		return fmt.Errorf("failed to auto-migrate group_config: %w", err)
	}
	if err := DB.AutoMigrate(&model.GroupAction{}); err != nil {
		return fmt.Errorf("failed to auto-migrate group_actions: %w", err)
	}
	if err := DB.AutoMigrate(
		&model.MetricTag{},
		&model.MetricMinute{},
		&model.MetricHour{},
		&model.MetricDay{},
	); err != nil {
		return fmt.Errorf("failed to auto-migrate metric tables: %w", err)
	}

	logger.Info("Database schema validation passed")
	return nil
}
