package alert

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"go.uber.org/zap"
)

// 告警防抖时间常量（防止重复告警）
const AlertDedupeWindow = 5 * time.Minute

// Evaluator 告警评估引擎
type Evaluator struct {
	mu            sync.RWMutex
	rules         []model.AlertRule
	evalInterval  time.Duration
	shutdown      chan struct{}
	wg            sync.WaitGroup
	metricsReader MetricsReader
}

// MetricsReader 指标数据读取接口
type MetricsReader interface {
	QueryMetrics(name string, tags map[string]string, windowMinutes int) ([]MetricPoint, error)
}

// MetricPoint 指标数据点
type MetricPoint struct {
	TimeKey string  `json:"timeKey"`
	Value   float64 `json:"value"`
}

// NewEvaluator 创建告警评估引擎
func NewEvaluator(evalInterval time.Duration, metricsReader MetricsReader) *Evaluator {
	return &Evaluator{
		evalInterval:  evalInterval,
		metricsReader: metricsReader,
		shutdown:      make(chan struct{}),
	}
}

// Start 启动评估引擎
func (e *Evaluator) Start(ctx context.Context) {
	// 加载规则
	e.loadRules()

	// 启动定期评估协程
	e.wg.Add(1)
	go func() {
		defer e.wg.Done()
		ticker := time.NewTicker(e.evalInterval)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				e.evaluateAll()
			case <-e.shutdown:
				return
			case <-ctx.Done():
				return
			}
		}
	}()

	logger.Info("Alert evaluator started", zap.Duration("interval", e.evalInterval))
}

// Stop 停止评估引擎
func (e *Evaluator) Stop() {
	close(e.shutdown)
	e.wg.Wait()
	logger.Info("Alert evaluator stopped")
}

// ReloadRules 重新加载规则
func (e *Evaluator) ReloadRules() {
	e.loadRules()
}

// loadRules 从数据库加载告警规则
func (e *Evaluator) loadRules() {
	e.mu.Lock()
	defer e.mu.Unlock()

	var rules []model.AlertRule
	if err := database.GetDB().Where("enabled = ?", true).Find(&rules).Error; err != nil {
		logger.Error("Failed to load alert rules", zap.Error(err))
		return
	}

	e.rules = rules
	logger.Info("Alert rules loaded", zap.Int("count", len(rules)))
}

// evaluateAll 评估所有规则
func (e *Evaluator) evaluateAll() {
	e.mu.RLock()
	rules := e.rules
	e.mu.RUnlock()

	for _, rule := range rules {
		e.evaluateRule(rule)
	}
}

// evaluateRule 评估单条规则
func (e *Evaluator) evaluateRule(rule model.AlertRule) {
	// 查询指标数据
	tags := make(map[string]string)
	if rule.Group != "" {
		tags["group"] = rule.Group
	}
	if rule.API != "" {
		tags["api"] = rule.API
	}

	points, err := e.metricsReader.QueryMetrics(rule.MetricName, tags, rule.Window)
	if err != nil {
		logger.Error("Failed to query metrics for alert",
			zap.String("rule", rule.Name),
			zap.Error(err))
		return
	}

	if len(points) == 0 {
		return // 没有数据，不触发告警
	}

	// 计算指标值（取窗口内的总和或平均值）
	var totalValue float64
	for _, p := range points {
		totalValue += p.Value
	}
	avgValue := totalValue / float64(len(points))

	// 根据操作符判断是否触发告警
	var triggered bool
	var currentValue float64

	// 对于 counter 类型指标，使用总和；对于 latency 类型，使用平均值
	if rule.MetricName == "invoke.total" || rule.MetricName == "invoke.latency" {
		currentValue = avgValue
	} else {
		currentValue = totalValue
	}

	triggered = e.checkThreshold(currentValue, rule.Operator, rule.Threshold)

	if triggered {
		e.triggerAlert(rule, currentValue)
	}
}

// checkThreshold 检查是否超过阈值
func (e *Evaluator) checkThreshold(value float64, operator string, threshold float64) bool {
	switch operator {
	case model.OpGreaterThan:
		return value > threshold
	case model.OpLessThan:
		return value < threshold
	case model.OpGreaterThanOrEqual:
		return value >= threshold
	case model.OpLessThanOrEqual:
		return value <= threshold
	case model.OpEqual:
		return value == threshold
	case model.OpNotEqual:
		return value != threshold
	default:
		return false
	}
}

// triggerAlert 触发告警
func (e *Evaluator) triggerAlert(rule model.AlertRule, currentValue float64) {
	// 检查是否最近已触发过（防抖，5 分钟内不重复触发）
	var recentCount int64
	database.GetDB().Table("alert_history").
		Where("rule_id = ? AND triggered_at > ?", time.Now().Add(-AlertDedupeWindow)).
		Count(&recentCount)

	if recentCount > 0 {
		return // 最近已触发过，跳过
	}

	// 确定告警级别
	level := model.AlertLevelInfo
	if currentValue > rule.Threshold*2 {
		level = model.AlertLevelCritical
	} else if currentValue > rule.Threshold*1.5 {
		level = model.AlertLevelWarning
	}

	// 创建告警记录
	history := model.AlertHistory{
		RuleID:       rule.ID,
		RuleName:     rule.Name,
		Group:        rule.Group,
		API:          rule.API,
		MetricName:   rule.MetricName,
		CurrentValue: currentValue,
		Threshold:    rule.Threshold,
		Operator:     rule.Operator,
		Level:        level,
		TriggeredAt:  time.Now(),
		Message: fmt.Sprintf("告警：%s - %s 的 %s 指标%s阈值 (%.2f %s %.2f)",
			rule.Name, rule.Group, rule.MetricName,
			rule.Operator, currentValue, rule.Operator, rule.Threshold),
	}

	// 发送通知
	if err := e.sendNotification(rule, &history); err != nil {
		history.NotifyError = err.Error()
		logger.Error("Failed to send alert notification",
			zap.String("rule", rule.Name),
			zap.Error(err))
	} else {
		history.Notified = true
	}

	// 保存到数据库
	if err := database.GetDB().Create(&history).Error; err != nil {
		logger.Error("Failed to save alert history",
			zap.String("rule", rule.Name),
			zap.Error(err))
	} else {
		logger.Warn("Alert triggered",
			zap.String("rule", rule.Name),
			zap.String("level", level),
			zap.Float64("value", currentValue))
	}
}

// sendNotification 发送告警通知
func (e *Evaluator) sendNotification(rule model.AlertRule, history *model.AlertHistory) error {
	// 发送 Webhook 通知
	if rule.WebhookURL != "" {
		if err := e.sendWebhook(rule.WebhookURL, history); err != nil {
			return fmt.Errorf("webhook failed: %w", err)
		}
	}

	// 发送邮件通知（预留接口）
	if rule.Email != "" {
		// TODO: 实现邮件发送
		logger.Info("Email notification not implemented yet",
			zap.String("email", rule.Email))
	}

	return nil
}

// sendWebhook 发送 Webhook 通知
func (e *Evaluator) sendWebhook(url string, history *model.AlertHistory) error {
	// TODO: 实现 Webhook 发送
	// 这里可以调用 net/http 发送 POST 请求
	logger.Debug("Webhook notification", zap.String("url", url))
	return nil
}

// DefaultMetricsReader 默认指标读取器
type DefaultMetricsReader struct{}

// NewDefaultMetricsReader 创建默认指标读取器
func NewDefaultMetricsReader() *DefaultMetricsReader {
	return &DefaultMetricsReader{}
}

// QueryMetrics 查询指标数据
func (r *DefaultMetricsReader) QueryMetrics(name string, tags map[string]string, windowMinutes int) ([]MetricPoint, error) {
	db := database.GetDB()
	if db == nil {
		return nil, fmt.Errorf("database not initialized")
	}

	// 构建查询
	query := db.Table("metric_minute").
		Select("time_key, value").
		Where("name = ?", name).
		Order("time_key DESC").
		Limit(windowMinutes)

	// 添加标签过滤
	if group, ok := tags["group"]; ok {
		query = query.Where("tag1 = ?", group)
	}
	if api, ok := tags["api"]; ok {
		query = query.Where("tag2 = ?", api)
	}

	var results []MetricPoint
	if err := query.Scan(&results).Error; err != nil {
		return nil, err
	}

	return results, nil
}
