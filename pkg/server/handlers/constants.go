package handlers

import "time"

// 时间阈值常量
const (
	// ClientInactiveThreshold 客户端非活跃时间阈值（5 分钟）
	// 超过此时间未活跃的客户端被视为离线/禁用状态
	ClientInactiveThreshold = 5 * time.Minute
)

// 默认 QPS 配置常量
const (
	// DefaultGroupQPS 默认分组 QPS 限制
	DefaultGroupQPS = 100.0
	// DefaultDeviceQPS 默认设备 QPS 限制
	DefaultDeviceQPS = 10.0
)

// 默认 Actions 列表
// 当设备连接到正式分组时，这些 Actions 会被自动添加到 group_actions 表中
var DefaultGroupActions = []string{"invoke", "execJs", "getHtml", "getCookie"}
