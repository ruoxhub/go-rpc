package config

import (
	"context"
	"strconv"
	"sync"
	"time"

	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"go.uber.org/zap"
)

// 配置键常量定义
const (
	// 用户注册相关
	ConfigKeyAllowRegister         = "sekiro.user.allowRegister"
	ConfigKeyDefaultQuotaUser      = "sekiro.defaultRegisterQuotaUser"
	ConfigKeyDefaultQuotaGroup     = "sekiro.defaultRegisterQuotaGroup"
	ConfigKeyDefaultQuotaPerDevice = "sekiro.defaultRegisterQuotaPerDevice"

	// 匿名访问相关
	ConfigKeyAllowAnonymousAccess  = "sekiro.allowAnonymousAccess"
	ConfigKeyAnonymousRateLimit    = "sekiro.anonymousAccessRateLimit"

	// 系统功能相关
	ConfigKeyDefendIdleInvoke      = "sekiro.defendIdleInvoke"
	ConfigKeySystemNotice          = "sekiro.systemNotice"
	ConfigKeyDocNotice             = "sekiro.docNotice"
	ConfigKeyOutIpTestUrl          = "sekiro.outIpTestUrl"

	// SSL 相关
	ConfigKeyUseCustomSSL          = "sekiro.useCustomSSLCertificate"
	ConfigKeyAutoGenSSLHosts       = "sekiro.autoGenSSLCertificateHostList"
	ConfigKeyOpen443Website        = "sekiro.open443Website"
)

// Service 配置服务接口
type Service interface {
	// Start 启动配置服务（后台刷新）
	Start(ctx context.Context, refreshInterval time.Duration) error
	// GetConfig 获取配置值（字符串）
	GetConfig(key string) string
	// GetConfigBool 获取配置值（布尔型）
	GetConfigBool(key string, defaultVal bool) bool
	// GetConfigFloat 获取配置值（浮点型）
	GetConfigFloat(key string, defaultVal float64) float64
	// GetConfigInt 获取配置值（整型）
	GetConfigInt(key string, defaultVal int) int
	// GetAllConfigs 获取所有配置
	GetAllConfigs() map[string]string
	// Refresh 从数据库刷新配置
	Refresh() error
}

// service 配置服务实现
type service struct {
	configs sync.Map // 内存缓存 key=ConfigKey, value=string
	mu      sync.RWMutex
}

// NewService 创建配置服务实例
func NewService() Service {
	return &service{
		configs: sync.Map{},
	}
}

// Start 启动配置服务（加载初始配置并启动后台刷新）
func (s *service) Start(ctx context.Context, refreshInterval time.Duration) error {
	// 初始加载
	if err := s.Refresh(); err != nil {
		logger.Error("初始加载配置失败", zap.Error(err))
		// 不返回错误，继续启动（使用空配置）
	}

	// 启动后台刷新 goroutine
	go s.startBackgroundRefresh(ctx, refreshInterval)

	return nil
}

// GetConfig 获取配置值
func (s *service) GetConfig(key string) string {
	if val, ok := s.configs.Load(key); ok {
		if str, ok := val.(string); ok {
			return str
		}
	}
	return ""
}

// GetConfigBool 获取布尔型配置
func (s *service) GetConfigBool(key string, defaultVal bool) bool {
	val := s.GetConfig(key)
	if val == "" {
		return defaultVal
	}

	// 支持多种布尔表示
	if val == "true" || val == "1" || val == "TRUE" || val == "True" {
		return true
	}
	if val == "false" || val == "0" || val == "FALSE" || val == "False" {
		return false
	}

	return defaultVal
}

// GetConfigFloat 获取浮点型配置
func (s *service) GetConfigFloat(key string, defaultVal float64) float64 {
	val := s.GetConfig(key)
	if val == "" {
		return defaultVal
	}

	result, err := strconv.ParseFloat(val, 64)
	if err != nil {
		logger.Warn("配置值转换失败，使用默认值", zap.String("key", key), zap.String("value", val), zap.Error(err))
		return defaultVal
	}

	return result
}

// GetConfigInt 获取整型配置
func (s *service) GetConfigInt(key string, defaultVal int) int {
	val := s.GetConfig(key)
	if val == "" {
		return defaultVal
	}

	result, err := strconv.Atoi(val)
	if err != nil {
		logger.Warn("配置值转换失败，使用默认值", zap.String("key", key), zap.String("value", val), zap.Error(err))
		return defaultVal
	}

	return result
}

// GetAllConfigs 获取所有配置
func (s *service) GetAllConfigs() map[string]string {
	result := make(map[string]string)
	s.configs.Range(func(key, value interface{}) bool {
		if k, ok := key.(string); ok {
			if v, ok := value.(string); ok {
				result[k] = v
			}
		}
		return true
	})
	return result
}

// Refresh 从数据库刷新配置
func (s *service) Refresh() error {
	db := database.GetDB()
	if db == nil {
		logger.Warn("数据库未初始化，跳过配置刷新")
		return nil
	}

	var configs []model.SysConfig
	if err := db.Find(&configs).Error; err != nil {
		logger.Error("查询配置失败", zap.Error(err))
		return err
	}

	// 创建新的配置映射
	newConfigs := make(map[string]string, len(configs))
	for _, cfg := range configs {
		newConfigs[cfg.ConfigKey] = cfg.ConfigValue
	}

	// 原子性替换所有配置
	s.configs = sync.Map{}
	for key, val := range newConfigs {
		s.configs.Store(key, val)
	}

	logger.Info("配置刷新成功", zap.Int("count", len(configs)))
	return nil
}

// startBackgroundRefresh 后台定期刷新配置
func (s *service) startBackgroundRefresh(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if err := s.Refresh(); err != nil {
				logger.Error("后台刷新配置失败", zap.Error(err))
			}
		case <-ctx.Done():
			logger.Info("停止配置后台刷新")
			return
		}
	}
}

// 确保 service 实现 Service 接口
var _ Service = (*service)(nil)
