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
	MetricTypeCounter   MetricType = "counter"
	MetricTypeGauge     MetricType = "gauge"
	MetricTypeHistogram MetricType = "histogram"
	MetricTypeLatency   MetricType = "latency"
)

// MetricCollector 指标采集器接口
type MetricCollector interface {
	Incr(name string, tags map[string]string, value float64)
	Set(name string, tags map[string]string, value float64)
	Observe(name string, tags map[string]string, value float64)
	RecordLatency(name string, tags map[string]string, durationMs float64)
	Shutdown()
}

type collector struct {
	mu       sync.Mutex
	buckets  map[string]*metricBucket
	interval time.Duration
	stopChan chan struct{}
	wg       sync.WaitGroup
	once     sync.Once
}

type metricBucket struct {
	Name         string
	TimeKey      string
	Tags         map[string]string
	Type         MetricType
	Value        float64
	Count        int64
	Sum          float64
	Observations []float64
}

const timeKeyMinute = "200601021504"
const hourFormat = "2006010215"
const dayFormat = "20060102"

// tagsMD5 生成 tags 的 MD5
func tagsMD5(tags map[string]string) string {
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

// makeKey 生成唯一的 bucket key
func makeKey(name string, tags map[string]string, metricType string) string {
	return fmt.Sprintf("%s:%s:%s", name, tagsMD5(tags), metricType)
}

// NewCollector 创建指标采集器
func NewCollector(interval time.Duration) MetricCollector {
	c := &collector{
		buckets:  make(map[string]*metricBucket),
		interval: interval,
		stopChan: make(chan struct{}),
	}
	c.wg.Add(2)
	go c.flushLoop()
	go c.rollupLoop()
	return c
}

// getOrCreateBucket 获取或创建 bucket（调用方须持有 c.mu）
func (c *collector) getOrCreateBucket(name string, tags map[string]string, mt MetricType) *metricBucket {
	key := makeKey(name, tags, string(mt))
	bucket, ok := c.buckets[key]
	if !ok {
		tagsCopy := make(map[string]string, len(tags))
		for k, v := range tags {
			tagsCopy[k] = v
		}
		bucket = &metricBucket{
			Name:    name,
			Tags:    tagsCopy,
			Type:    mt,
			TimeKey: time.Now().Format(timeKeyMinute),
		}
		if mt == MetricTypeHistogram {
			bucket.Observations = make([]float64, 0)
		}
		c.buckets[key] = bucket
	}
	return bucket
}

func (c *collector) Incr(name string, tags map[string]string, value float64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	bucket := c.getOrCreateBucket(name, tags, MetricTypeCounter)
	bucket.Value += value
	bucket.Count++
}

func (c *collector) Set(name string, tags map[string]string, value float64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	bucket := c.getOrCreateBucket(name, tags, MetricTypeGauge)
	bucket.Value = value
	bucket.Count++
}

func (c *collector) Observe(name string, tags map[string]string, value float64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	bucket := c.getOrCreateBucket(name, tags, MetricTypeHistogram)
	bucket.Value += value
	bucket.Count++
	bucket.Sum += value
	bucket.Observations = append(bucket.Observations, value)
}

func (c *collector) RecordLatency(name string, tags map[string]string, durationMs float64) {
	c.Observe(name+".latency", tags, durationMs)
}

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

func (c *collector) flush() {
	c.mu.Lock()
	buckets := c.buckets
	c.buckets = make(map[string]*metricBucket)
	c.mu.Unlock()

	var metrics []model.MetricMinute
	for _, bucket := range buckets {
		percentiles := c.calculatePercentiles(bucket)
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

	for _, bucket := range buckets {
		if len(bucket.Tags) == 0 {
			continue
		}
		db.Exec(`
			INSERT INTO metric_tag (name, tag1_name, tag2_name, tag3_name)
			VALUES (?, 'group', 'device_id', 'api')
			ON CONFLICT (name) DO NOTHING
		`, bucket.Name)

		for _, suffix := range []string{".p50", ".p90", ".p99"} {
			db.Exec(`
				INSERT INTO metric_tag (name, tag1_name, tag2_name)
				VALUES (?, 'group', 'api')
				ON CONFLICT (name) DO NOTHING
			`, bucket.Name+suffix)
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

	sorted := make([]float64, len(bucket.Observations))
	copy(sorted, bucket.Observations)
	sort.Float64s(sorted)

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
	md5 := tagsMD5(bucket.Tags)
	records := []model.MetricMinute{{
		Name:    bucket.Name,
		TimeKey: bucket.TimeKey,
		TagsMD5: md5,
		Type:    string(bucket.Type),
		Value:   bucket.Value,
		Tag1:    bucket.Tags["group"],
		Tag2:    bucket.Tags["device_id"],
		Tag3:    bucket.Tags["api"],
	}}

	for p, v := range percentiles {
		records = append(records, model.MetricMinute{
			Name:    fmt.Sprintf("%s.p%d", bucket.Name, int(p)),
			TimeKey: bucket.TimeKey,
			TagsMD5: md5,
			Type:    "latency",
			Value:   v,
			Tag1:    bucket.Tags["group"],
			Tag2:    bucket.Tags["api"],
		})
	}

	return records
}

func (c *collector) Shutdown() {
	c.once.Do(func() {
		close(c.stopChan)
		c.wg.Wait()
		c.flush()
	})
}

func (c *collector) rollupLoop() {
	defer c.wg.Done()
	ticker := time.NewTicker(1 * time.Hour)
	defer ticker.Stop()

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

// rollup 执行一次聚合写入
func (c *collector) rollup(targetTable, sourceTable, timeKeyColumn, timeKeyParam, timeKeyFilter, aggFn, typeFilter string) {
	db := database.GetDB()
	if db == nil {
		return
	}
	query := fmt.Sprintf(`
		INSERT INTO %s (name, %s, tags_md5, tag1, tag2, tag3, tag4, tag5, type, value, create_time)
		SELECT name, ?, tags_md5, tag1, tag2, tag3, tag4, tag5, type, %s(value), MIN(create_time)
		FROM %s
		WHERE time_key LIKE ? AND %s
		GROUP BY name, tags_md5, tag1, tag2, tag3, tag4, tag5, type
		ON CONFLICT (name, tags_md5, %s)
		DO UPDATE SET value = EXCLUDED.value
	`, targetTable, timeKeyColumn, aggFn, sourceTable, typeFilter, timeKeyColumn)
	if err := db.Exec(query, timeKeyParam, timeKeyFilter).Error; err != nil {
		logger.Errorf("Failed to rollup %s metrics to %s: %v", typeFilter, targetTable, err)
	}
}

func (c *collector) runRollupAndRetention() {
	db := database.GetDB()
	if db == nil {
		return
	}

	now := time.Now()
	prevHour := now.Add(-1 * time.Hour)
	prevHourKey := prevHour.Format(hourFormat)

	logger.Infof("Starting metrics hourly rollup for time_keyPrefix: %s", prevHourKey)

	c.rollup("metric_hour", "metric_minute", "time_key", prevHourKey, prevHourKey+"%", "SUM", "type = 'counter'")
	c.rollup("metric_hour", "metric_minute", "time_key", prevHourKey, prevHourKey+"%", "AVG", "(type = 'gauge' OR type = 'latency')")

	if now.Hour() == 0 {
		prevDay := now.AddDate(0, 0, -1)
		prevDayKey := prevDay.Format(dayFormat)

		logger.Infof("Starting metrics daily rollup for time_keyPrefix: %s", prevDayKey)

		c.rollup("metric_day", "metric_hour", "time_key", prevDayKey, prevDayKey+"%", "SUM", "type = 'counter'")
		c.rollup("metric_day", "metric_hour", "time_key", prevDayKey, prevDayKey+"%", "AVG", "(type = 'gauge' OR type = 'latency')")

		logger.Info("Cleaning expired metrics data...")
		if err := db.Exec(`DELETE FROM metric_minute WHERE create_time < ?`, now.AddDate(0, 0, -7)).Error; err != nil {
			logger.Errorf("Failed to clean metric_minute: %v", err)
		}
		if err := db.Exec(`DELETE FROM metric_hour WHERE create_time < ?`, now.AddDate(0, 0, -30)).Error; err != nil {
			logger.Errorf("Failed to clean metric_hour: %v", err)
		}
	}
}
