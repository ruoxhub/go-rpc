package alert

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
	"go.uber.org/zap"
)

// 告警防抖时间常量（防止重复告警）
const AlertDedupeWindow = 5 * time.Minute

// AlertRepo defines the alert data access interface used by the evaluator.
type AlertRepo interface {
	FindAllEnabledRules() ([]model.AlertRule, error)
	CountRecentHistory(ruleID int64, since time.Time) (int64, error)
	CreateHistory(history *model.AlertHistory) error
}

// MetricTagMapping maps metric tag names to column names.
type MetricTagMapping struct {
	Tag1Name string
	Tag2Name string
	Tag3Name string
	Tag4Name string
	Tag5Name string
}

// MetricMinutePoint is a lightweight metric data point.
type MetricMinutePoint struct {
	TimeKey string
	Value   float64
}

// MetricQueryStore defines the metric query interface used by the evaluator's DefaultMetricsReader.
type MetricQueryStore interface {
	QueryMetricMinutes(name string, tags map[string]string, tagMapping *MetricTagMapping, limit int) ([]MetricMinutePoint, error)
	LoadMetricTagMapping(name string) (*MetricTagMapping, error)
}

// RepoMetricQueryStore adapts repository.MetricStore to MetricQueryStore by converting types.
type RepoMetricQueryStore struct {
	Inner repository.MetricStore
}

func (a *RepoMetricQueryStore) QueryMetricMinutes(name string, tags map[string]string, tagMapping *MetricTagMapping, limit int) ([]MetricMinutePoint, error) {
	var repoMapping *repository.MetricTagMapping
	if tagMapping != nil {
		repoMapping = &repository.MetricTagMapping{
			Tag1Name: tagMapping.Tag1Name,
			Tag2Name: tagMapping.Tag2Name,
			Tag3Name: tagMapping.Tag3Name,
			Tag4Name: tagMapping.Tag4Name,
			Tag5Name: tagMapping.Tag5Name,
		}
	}
	repoPoints, err := a.Inner.QueryMetricMinutes(name, tags, repoMapping, limit)
	if err != nil {
		return nil, err
	}
	result := make([]MetricMinutePoint, len(repoPoints))
	for i, p := range repoPoints {
		result[i] = MetricMinutePoint{TimeKey: p.TimeKey, Value: p.Value}
	}
	return result, nil
}

func (a *RepoMetricQueryStore) LoadMetricTagMapping(name string) (*MetricTagMapping, error) {
	m, err := a.Inner.LoadMetricTagMapping(name)
	if err != nil {
		return nil, err
	}
	if m == nil {
		return nil, nil
	}
	return &MetricTagMapping{
		Tag1Name: m.Tag1Name,
		Tag2Name: m.Tag2Name,
		Tag3Name: m.Tag3Name,
		Tag4Name: m.Tag4Name,
		Tag5Name: m.Tag5Name,
	}, nil
}

// Evaluator 告警评估引擎
type Evaluator struct {
	mu            sync.RWMutex
	rules         []model.AlertRule
	evalInterval  time.Duration
	shutdown      chan struct{}
	wg            sync.WaitGroup
	metricsReader MetricsReader
	notifier      Notifier
	alertRepo     AlertRepo
	metricStore   MetricQueryStore
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
		notifier:      NewDefaultNotifier(),
	}
}

// SetAlertRepo injects the AlertRepository for rule loading and history persistence.
func (e *Evaluator) SetAlertRepo(repo AlertRepo) {
	e.alertRepo = repo
}

// SetMetricStore injects the MetricQueryStore for the DefaultMetricsReader.
func (e *Evaluator) SetMetricStore(store MetricQueryStore) {
	e.metricStore = store
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

// SetNotifier 设置通知发送器
func (e *Evaluator) SetNotifier(notifier Notifier) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.notifier = notifier
}

// SetSMTPConfig 设置 SMTP 配置（便捷方法）
func (e *Evaluator) SetSMTPConfig(config SMTPConfig) {
	if e.notifier != nil {
		if dn, ok := e.notifier.(*DefaultNotifier); ok {
			dn.SetSMTPConfig(config)
		}
	}
}

// loadRules 从数据库加载告警规则
func (e *Evaluator) loadRules() {
	if e.alertRepo == nil {
		return
	}
	e.mu.Lock()
	defer e.mu.Unlock()

	rules, err := e.alertRepo.FindAllEnabledRules()
	if err != nil {
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
	if e.alertRepo == nil {
		return
	}

	recentCount, err := e.alertRepo.CountRecentHistory(rule.ID, time.Now().Add(-AlertDedupeWindow))
	if err != nil {
		logger.Error("Failed to check alert dedupe window",
			zap.String("rule", rule.Name),
			zap.Error(err))
		return
	}

	if recentCount > 0 {
		return
	}

	level := alertLevel(rule, currentValue)
	history := newAlertHistory(rule, currentValue, level)

	if err := e.sendNotification(rule, &history); err != nil {
		history.NotifyError = err.Error()
		logger.Error("Failed to send alert notification",
			zap.String("rule", rule.Name),
			zap.Error(err))
	} else {
		history.Notified = true
	}

	if err := e.alertRepo.CreateHistory(&history); err != nil {
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

func alertLevel(rule model.AlertRule, currentValue float64) string {
	if currentValue > rule.Threshold*2 {
		return model.AlertLevelCritical
	}
	if currentValue > rule.Threshold*1.5 {
		return model.AlertLevelWarning
	}
	return model.AlertLevelInfo
}

func newAlertHistory(rule model.AlertRule, currentValue float64, level string) model.AlertHistory {
	return model.AlertHistory{
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
}

// sendNotification 发送告警通知
func (e *Evaluator) sendNotification(rule model.AlertRule, history *model.AlertHistory) error {
	return SendAlertNotification(e.notifier, rule, history)
}

// DefaultMetricsReader 默认指标读取器
type DefaultMetricsReader struct {
	store MetricQueryStore
}

// NewDefaultMetricsReader 创建默认指标读取器
func NewDefaultMetricsReader() *DefaultMetricsReader {
	return &DefaultMetricsReader{}
}

// SetStore injects the MetricQueryStore for metric queries.
func (r *DefaultMetricsReader) SetStore(store MetricQueryStore) {
	r.store = store
}

// QueryMetrics 查询指标数据
func (r *DefaultMetricsReader) QueryMetrics(name string, tags map[string]string, windowMinutes int) ([]MetricPoint, error) {
	if r.store == nil {
		return nil, fmt.Errorf("metric store not initialized")
	}

	mapping, err := r.store.LoadMetricTagMapping(name)
	if err != nil {
		logger.Debug("Failed to load metric tag mapping, using default tags",
			zap.String("name", name), zap.Error(err))
	}

	points, err := r.store.QueryMetricMinutes(name, tags, mapping, windowMinutes)
	if err != nil {
		return nil, err
	}

	result := make([]MetricPoint, len(points))
	for i, p := range points {
		result[i] = MetricPoint{TimeKey: p.TimeKey, Value: p.Value}
	}
	return result, nil
}
