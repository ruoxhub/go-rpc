package metrics

import (
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"sort"
	"sync"
	"time"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/model"
	"go.uber.org/zap"
)

// MetricType 指标类型
type MetricType string

const (
	MetricTypeCounter   MetricType = "counter"   // 计数器（累加）
	MetricTypeGauge     MetricType = "gauge"     // 仪表（瞬时值）
	MetricTypeHistogram MetricType = "histogram" // 直方图（分布）
	MetricTypeLatency   MetricType = "latency"   // 延迟指标
)

// MetricCollector 指标采集器接口
type MetricCollector interface {
	// Incr 增加计数
	Incr(name string, tags map[string]string, value float64)
	// Set 设置仪表值
	Set(name string, tags map[string]string, value float64)
	// Observe 观察值（用于直方图）
	Observe(name string, tags map[string]string, value float64)
	// RecordLatency 记录延迟（自动计算 P50/P90/P99）
	RecordLatency(name string, tags map[string]string, durationMs float64)
	// Shutdown 停止后台刷新并尽力落盘剩余指标
	Shutdown()
}

// collector 采集器实现
type collector struct {
	mu       sync.Mutex
	buckets  map[string]*metricBucket
	interval time.Duration
	stopChan chan struct{}
	wg       sync.WaitGroup
	once     sync.Once
}

// metricBucket 指标桶（用于批量写入）
type metricBucket struct {
	Name         string
	TimeKey      string
	Tags         map[string]string
	Type         MetricType
	Value        float64
	Count        int64
	Sum          float64
	Observations []float64 // 存储所有观测值用于计算百分位数
}

// NewCollector 创建指标采集器
func NewCollector(interval time.Duration) MetricCollector {
	c := &collector{
		buckets:  make(map[string]*metricBucket),
		interval: interval,
		stopChan: make(chan struct{}),
	}
	// 启动定期刷新和聚合协程
	c.wg.Add(2)
	go c.flushLoop()
	go c.rollupLoop()
	return c
}

// Incr 增加计数
func (c *collector) Incr(name string, tags map[string]string, value float64) {
	c.mu.Lock()
	defer c.mu.Unlock()

	key := c.makeKey(name, tags, string(MetricTypeCounter))
	bucket, ok := c.buckets[key]
	if !ok {
		bucket = &metricBucket{
			Name:    name,
			Tags:    tags,
			Type:    MetricTypeCounter,
			TimeKey: time.Now().Format("200601021504"), // 分钟级
		}
		c.buckets[key] = bucket
	}
	bucket.Value += value
	bucket.Count++
}

// Set 设置仪表值
func (c *collector) Set(name string, tags map[string]string, value float64) {
	c.mu.Lock()
	defer c.mu.Unlock()

	key := c.makeKey(name, tags, string(MetricTypeGauge))
	bucket, ok := c.buckets[key]
	if !ok {
		bucket = &metricBucket{
			Name:    name,
			Tags:    tags,
			Type:    MetricTypeGauge,
			TimeKey: time.Now().Format("200601021504"),
		}
		c.buckets[key] = bucket
	}
	bucket.Value = value
	bucket.Count++
}

// Observe 观察值（用于直方图）
func (c *collector) Observe(name string, tags map[string]string, value float64) {
	c.mu.Lock()
	defer c.mu.Unlock()

	key := c.makeKey(name, tags, string(MetricTypeHistogram))
	bucket, ok := c.buckets[key]
	if !ok {
		bucket = &metricBucket{
			Name:         name,
			Tags:         tags,
			Type:         MetricTypeHistogram,
			TimeKey:      time.Now().Format("200601021504"),
			Observations: make([]float64, 0),
		}
		c.buckets[key] = bucket
	}
	bucket.Value += value
	bucket.Count++
	bucket.Sum += value
	bucket.Observations = append(bucket.Observations, value)
}

// RecordLatency 记录延迟
func (c *collector) RecordLatency(name string, tags map[string]string, durationMs float64) {
	c.Observe(name+".latency", tags, durationMs)
}

// makeKey 生成唯一的 bucket key
func (c *collector) makeKey(name string, tags map[string]string, metricType string) string {
	// 将 tags 排序后生成 MD5
	keys := make([]string, 0, len(tags))
	for k := range tags {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	h := md5.New()
	for _, k := range keys {
		h.Write([]byte(fmt.Sprintf("%s=%s,", k, tags[k])))
	}
	tagsMD5 := hex.EncodeToString(h.Sum(nil))

	return fmt.Sprintf("%s:%s:%s", name, tagsMD5, metricType)
}

// tagsMD5 生成 tags 的 MD5
func (c *collector) tagsMD5(tags map[string]string) string {
	keys := make([]string, 0, len(tags))
	for k := range tags {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	h := md5.New()
	for _, k := range keys {
		h.Write([]byte(fmt.Sprintf("%s=%s,", k, tags[k])))
	}
	return hex.EncodeToString(h.Sum(nil))
}

// flushLoop 定期刷新协程
func (c *collector) flushLoop() {
	defer c.wg.Done()
	ticker := time.NewTicker(c.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			c.flush()
		case <-c.stopChan:
			return
		}
	}
}

// flush 批量写入数据库
func (c *collector) flush() {
	c.mu.Lock()
	buckets := c.buckets
	c.buckets = make(map[string]*metricBucket)
	c.mu.Unlock()

	var metrics []model.MetricMinute
	for _, bucket := range buckets {
		// 计算百分位数
		percentiles := c.calculatePercentiles(bucket)

		// 创建指标记录
		metrics = append(metrics, c.toMetricRecords(bucket, percentiles)...)
	}

	if len(metrics) == 0 {
		return
	}

	db := database.GetDB()
	if db == nil {
		logger.Warn("metric collector flush skipped: database not initialized")
		return
	}

	// 动态注册标签映射关系到 metric_tag 表
	for _, bucket := range buckets {
		if len(bucket.Tags) > 0 {
			db.Exec(`
				INSERT INTO metric_tag (name, tag1_name, tag2_name, tag3_name)
				VALUES (?, 'group', 'device_id', 'api')
				ON CONFLICT (name) DO NOTHING
			`, bucket.Name)

			db.Exec(`
				INSERT INTO metric_tag (name, tag1_name, tag2_name)
				VALUES (?, 'group', 'api')
				ON CONFLICT (name) DO NOTHING
			`, bucket.Name+".p50")
			db.Exec(`
				INSERT INTO metric_tag (name, tag1_name, tag2_name)
				VALUES (?, 'group', 'api')
				ON CONFLICT (name) DO NOTHING
			`, bucket.Name+".p90")
			db.Exec(`
				INSERT INTO metric_tag (name, tag1_name, tag2_name)
				VALUES (?, 'group', 'api')
				ON CONFLICT (name) DO NOTHING
			`, bucket.Name+".p99")
		}
	}

	if err := db.CreateInBatches(metrics, 100).Error; err != nil {
		logger.Error("metric collector flush failed", zap.Error(err), zap.Int("count", len(metrics)))
	}
}

// calculatePercentiles 计算百分位数 (P50/P90/P99)
func (c *collector) calculatePercentiles(bucket *metricBucket) map[float64]float64 {
	if len(bucket.Observations) == 0 {
		return nil
	}

	// 排序观测值
	sorted := make([]float64, len(bucket.Observations))
	copy(sorted, bucket.Observations)
	sort.Float64s(sorted)

	// 计算百分位数
	calcPercentile := func(p float64) float64 {
		idx := int(float64(len(sorted)-1) * p / 100)
		return sorted[idx]
	}

	return map[float64]float64{
		50: calcPercentile(50),
		90: calcPercentile(90),
		99: calcPercentile(99),
	}
}

// toMetricRecords 转换为数据库记录
func (c *collector) toMetricRecords(bucket *metricBucket, percentiles map[float64]float64) []model.MetricMinute {
	var records []model.MetricMinute

	// 基础指标
	records = append(records, model.MetricMinute{
		Name:    bucket.Name,
		TimeKey: bucket.TimeKey,
		TagsMD5: c.tagsMD5(bucket.Tags),
		Type:    string(bucket.Type),
		Value:   bucket.Value,
		Tag1:    bucket.Tags["group"],
		Tag2:    bucket.Tags["device_id"],
		Tag3:    bucket.Tags["api"],
	})

	// 延迟百分位数
	for p, v := range percentiles {
		records = append(records, model.MetricMinute{
			Name:    fmt.Sprintf("%s.p%d", bucket.Name, int(p)),
			TimeKey: bucket.TimeKey,
			TagsMD5: c.tagsMD5(bucket.Tags),
			Type:    "latency",
			Value:   v,
			Tag1:    bucket.Tags["group"],
			Tag2:    bucket.Tags["api"],
		})
	}

	return records
}

// Shutdown 停止后台刷新并落盘剩余指标
func (c *collector) Shutdown() {
	c.once.Do(func() {
		close(c.stopChan)
		c.wg.Wait()
		c.flush()
	})
}

// rollupLoop 定期聚合小时和天级指标协程
func (c *collector) rollupLoop() {
	defer c.wg.Done()
	// 每小时检查并触发一次聚合
	ticker := time.NewTicker(1 * time.Hour)
	defer ticker.Stop()

	// 启动时延迟 5 秒后首次尝试，检查并补全此前数据
	select {
	case <-time.After(5 * time.Second):
		c.runRollupAndRetention()
	case <-c.stopChan:
		return
	}

	for {
		select {
		case <-ticker.C:
			c.runRollupAndRetention()
		case <-c.stopChan:
			return
		}
	}
}

// runRollupAndRetention 执行小时/天级 Rollup 以及过期数据清理
func (c *collector) runRollupAndRetention() {
	db := database.GetDB()
	if db == nil {
		return
	}

	now := time.Now()
	// 聚合前一小时的数据
	prevHour := now.Add(-1 * time.Hour)
	timeKeyMinPrefix := prevHour.Format("2006010215") // yyyyMMddHH
	timeKeyHour := prevHour.Format("2006010215")     // yyyyMMddHH

	logger.Infof("Starting metrics hourly rollup for time_keyPrefix: %s", timeKeyMinPrefix)

	// 1. 小时级 Rollup (counter 累加)
	err := db.Exec(`
		INSERT INTO metric_hour (name, time_key, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
		SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, SUM(value), MIN(create_time)
		FROM metric_minute
		WHERE time_key LIKE ? AND type = 'counter'
		GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
		ON CONFLICT (name, tags_md5, time_key) 
		DO UPDATE SET value = EXCLUDED.value
	`, timeKeyHour, timeKeyMinPrefix+"%").Error
	if err != nil {
		logger.Errorf("Failed to rollup counter metrics to hour: %v", err)
	}

	// 2. 小时级 Rollup (gauge / latency 均值)
	err = db.Exec(`
		INSERT INTO metric_hour (name, time_key, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
		SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, AVG(value), MIN(create_time)
		FROM metric_minute
		WHERE time_key LIKE ? AND (type = 'gauge' OR type = 'latency')
		GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
		ON CONFLICT (name, tags_md5, time_key) 
		DO UPDATE SET value = EXCLUDED.value
	`, timeKeyHour, timeKeyMinPrefix+"%").Error
	if err != nil {
		logger.Errorf("Failed to rollup gauge/latency metrics to hour: %v", err)
	}

	// 3. 天级 Rollup (每天 0 点至 1 点之间触发，聚合前一天 24 小时的数据)
	if now.Hour() == 0 {
		prevDay := now.AddDate(0, 0, -1)
		timeKeyHourPrefix := prevDay.Format("20060102") // yyyyMMdd
		timeKeyDay := prevDay.Format("20060102")        // yyyyMMdd

		logger.Infof("Starting metrics daily rollup for time_keyPrefix: %s", timeKeyHourPrefix)

		// 天级 Rollup (counter 累加)
		err = db.Exec(`
			INSERT INTO metric_day (name, time_key, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
			SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, SUM(value), MIN(create_time)
			FROM metric_hour
			WHERE time_key LIKE ? AND type = 'counter'
			GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
			ON CONFLICT (name, tags_md5, time_key) 
			DO UPDATE SET value = EXCLUDED.value
		`, timeKeyDay, timeKeyHourPrefix+"%").Error
		if err != nil {
			logger.Errorf("Failed to rollup counter metrics to day: %v", err)
		}

		// 天级 Rollup (gauge / latency 均值)
		err = db.Exec(`
			INSERT INTO metric_day (name, time_key, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
			SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, AVG(value), MIN(create_time)
			FROM metric_hour
			WHERE time_key LIKE ? AND (type = 'gauge' OR type = 'latency')
			GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
			ON CONFLICT (name, tags_md5, time_key) 
			DO UPDATE SET value = EXCLUDED.value
		`, timeKeyDay, timeKeyHourPrefix+"%").Error
		if err != nil {
			logger.Errorf("Failed to rollup gauge/latency metrics to day: %v", err)
		}

		// 4. 数据过期清理 (分钟数据保留 7 天，小时数据保留 30 天)
		sevenDaysAgo := now.AddDate(0, 0, -7)
		thirtyDaysAgo := now.AddDate(0, 0, -30)

		logger.Info("Cleaning expired metrics data...")

		if err := db.Exec(`DELETE FROM metric_minute WHERE create_time < ?`, sevenDaysAgo).Error; err != nil {
			logger.Errorf("Failed to clean metric_minute: %v", err)
		}
		if err := db.Exec(`DELETE FROM metric_hour WHERE create_time < ?`, thirtyDaysAgo).Error; err != nil {
			logger.Errorf("Failed to clean metric_hour: %v", err)
		}
	}
}
