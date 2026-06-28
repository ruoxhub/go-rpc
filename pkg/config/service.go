package config

import (
	"hash/fnv"
	"sort"
	"strconv"
	"sync"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
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
	ConfigKeyAllowAnonymousAccess = "sekiro.allowAnonymousAccess"
	ConfigKeyAnonymousRateLimit   = "sekiro.anonymousAccessRateLimit"

	// 系统功能相关
	ConfigKeyDefendIdleInvoke = "sekiro.defendIdleInvoke"
	ConfigKeySystemNotice     = "sekiro.systemNotice"
	ConfigKeyDocNotice        = "sekiro.docNotice"
	ConfigKeyOutIpTestUrl     = "sekiro.outIpTestUrl"

	// SSL 相关
	ConfigKeyUseCustomSSL    = "sekiro.useCustomSSLCertificate"
	ConfigKeyAutoGenSSLHosts = "sekiro.autoGenSSLCertificateHostList"
	ConfigKeyOpen443Website  = "sekiro.open443Website"

	// 全局 IP 白名单
	ConfigKeyAllowedIPs = "sekiro.allowedIPs"
)

// Service 配置服务接口
type Service interface {
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
	// SetDependencies 注入 repository 和 eventBus（DB 就绪后调用）
	SetDependencies(repo repository.SysConfigRepository, eb *eventbus.EventBus)
	// Refresh 从数据库刷新配置。repo 为 nil 时跳过刷新并返回 nil。
	Refresh() error
}

// service 配置服务实现
type service struct {
	configs         sync.Map // 内存缓存 key=ConfigKey, value=string
	mu              sync.RWMutex
	lastConfigsHash uint64 // 上一次配置的哈希值，用于检测变化
	repo            repository.SysConfigRepository
	eventBus        *eventbus.EventBus
}

// NewService 创建配置服务实例
func NewService() Service {
	return &service{
		configs: sync.Map{},
	}
}

// SetDependencies 注入 repository 和 eventBus（DB 就绪后调用）
func (s *service) SetDependencies(repo repository.SysConfigRepository, eb *eventbus.EventBus) {
	s.repo = repo
	s.eventBus = eb
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

	result, err := strconv.ParseBool(val)
	if err != nil {
		return defaultVal
	}
	return result
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
	if s.repo == nil {
		logger.Warn("配置仓库未初始化，跳过配置刷新")
		return nil
	}

	configs, err := s.repo.FindAll()
	if err != nil {
		logger.Error("查询配置失败", zap.Error(err))
		return err
	}

	// 创建新的配置映射
	newConfigs := make(map[string]string, len(configs))
	for _, cfg := range configs {
		newConfigs[cfg.ConfigKey] = cfg.ConfigValue
	}

	// 计算新配置的哈希值，用于检测变化
	newHash := s.computeConfigsHash(newConfigs)

	// 对比哈希值，只有配置真正变化时才更新
	s.mu.Lock()
	hasChanged := s.lastConfigsHash != newHash
	if hasChanged {
		// 计算变更 key 集合（需要在替换前对比）
		changedKeys := s.diffConfigKeys(newConfigs)

		// 原子性替换所有配置
		s.configs = sync.Map{}
		for key, val := range newConfigs {
			s.configs.Store(key, val)
		}
		s.lastConfigsHash = newHash
		s.mu.Unlock()

		logger.Info("配置已更新", zap.Int("count", len(configs)))

		// 发布配置变更事件
		if s.eventBus != nil && len(changedKeys) > 0 {
			s.eventBus.Publish(eventbus.EventConfigChanged, eventbus.ConfigChangedEvent{
				Keys: changedKeys,
			})
			logger.Info("发布配置变更事件", zap.Strings("keys", changedKeys))
		}
	} else {
		s.mu.Unlock()
	}

	return nil
}

// computeConfigsHash 计算配置映射的哈希值
func (s *service) computeConfigsHash(configs map[string]string) uint64 {
	h := fnv.New64a()
	// 为了确定性，按 key 排序后计算
	keys := make([]string, 0, len(configs))
	for k := range configs {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	for _, k := range keys {
		h.Write([]byte(k))
		h.Write([]byte("="))
		h.Write([]byte(configs[k]))
		h.Write([]byte("\n"))
	}
	return h.Sum64()
}

// diffConfigKeys 对比新旧配置，返回变更 key 集合
func (s *service) diffConfigKeys(newConfigs map[string]string) []string {
	var changed []string
	oldKeys := make(map[string]bool)

	s.configs.Range(func(key, value interface{}) bool {
		if k, ok := key.(string); ok {
			oldKeys[k] = true
			if newVal, exists := newConfigs[k]; !exists || newVal != value.(string) {
				changed = append(changed, k)
			}
		}
		return true
	})

	for k := range newConfigs {
		if !oldKeys[k] {
			changed = append(changed, k)
		}
	}

	return changed
}

// 确保 service 实现 Service 接口
var _ Service = (*service)(nil)
