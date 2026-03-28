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
		&model.TraceRecord{},
		&model.AlertRule{},
		&model.AlertHistory{},
	)
	if err != nil {
		return err
	}

	// 创建默认管理员用户
	if err := createDefaultAdminUser(); err != nil {
		return err
	}

	// 创建默认系统配置
	return createDefaultSysConfigs()
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

// createDefaultSysConfigs 创建默认系统配置
func createDefaultSysConfigs() error {
	defaultConfigs := []struct {
		comment string
		key     string
		value   string
	}{
		{"是否允许注册用户", "sekiro.user.allowRegister", "true"},
		{"出口 ip 探测 URL", "sekiro.outIpTestUrl", "http://api.ipify.org"},
		{"系统通告信息", "sekiro.systemNotice", ""},
		{"文档首页通告信息", "sekiro.docNotice", ""},
		{"是否允许匿名访问", "sekiro.allowAnonymousAccess", "true"},
		{"匿名访问 qps 限制", "sekiro.anonymousAccessRateLimit", "10"},
		{"注册用户默认 qps 限制", "sekiro.defaultRegisterQuotaUser", "10"},
		{"注册 group 默认 qps 限制", "sekiro.defaultRegisterQuotaGroup", "100"},
		{"设备默认 qps 限制", "sekiro.defaultRegisterQuotaPerDevice", "10"},
		{"使用自定义 ssl 证书", "sekiro.useCustomSSLCertificate", "false"},
		{"为配置的 host 自动生成 ssl 证书", "sekiro.autoGenSSLCertificateHostList", ""},
		{"开启 443 服务端口", "sekiro.open443Website", "false"},
		{"空转调用保护", "sekiro.defendIdleInvoke", "true"},
	}

	for _, cfg := range defaultConfigs {
		var count int64
		DB.Model(&model.SysConfig{}).Where("config_key = ?", cfg.key).Count(&count)
		if count == 0 {
			sysConfig := model.SysConfig{
				ConfigComment: cfg.comment,
				ConfigKey:     cfg.key,
				ConfigValue:   cfg.value,
				CreateTime:    time.Now(),
			}
			if err := DB.Create(&sysConfig).Error; err != nil {
				return fmt.Errorf("failed to create config %s: %w", cfg.key, err)
			}
		}
	}
	return nil
}
