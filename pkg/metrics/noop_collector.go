package metrics

// noopCollector 空操作收集器，用于 metrics==nil 时避免空指针
type noopCollector struct{}

func (n *noopCollector) Incr(name string, tags map[string]string, value float64)        {}
func (n *noopCollector) Set(name string, tags map[string]string, value float64)         {}
func (n *noopCollector) Observe(name string, tags map[string]string, value float64)     {}
func (n *noopCollector) RecordLatency(name string, tags map[string]string, ms float64)  {}
func (n *noopCollector) Shutdown()                                                      {}

// NewNoopCollector 返回一个空操作收集器实例
func NewNoopCollector() MetricCollector {
	return &noopCollector{}
}
