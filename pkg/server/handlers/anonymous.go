package handlers

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/database"
)

// AnonymousGroupHandler 匿名分组处理器
type AnonymousGroupHandler struct{}

// NewAnonymousGroupHandler 创建匿名分组处理器
func NewAnonymousGroupHandler() *AnonymousGroupHandler {
	return &AnonymousGroupHandler{}
}

// AnonymousGroupVO 匿名分组 VO
type AnonymousGroupVO struct {
	GroupName        string `json:"groupName"`
	AvailableClients int64  `json:"availableClients"`
	DisabledClients  int64  `json:"disabledClients"`
	TotalClients     int64  `json:"totalClients"`
}

// List 获取匿名分组列表
// 匿名分组定义：存在于 group_device 表中，但其 group_name 不在 group_config 表中的设备
func (h *AnonymousGroupHandler) List(c *gin.Context) {
	db := database.GetDB()

	// 子查询：获取所有已注册分组的 group_name
	// 然后查询不在这个列表中的设备，按 group_name 分组统计
	var devices []struct {
		GroupName      string    `json:"group_name"`
		LastActiveTime time.Time `json:"last_active_time"`
	}

	// 查询所有设备，其 group_name 不在 group_config 表中
	if err := db.Table("group_device gd").
		Where("NOT EXISTS (SELECT 1 FROM group_config gc WHERE gc.group_name = gd.group_name)").
		Find(&devices).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 如果没有任何匿名设备，直接返回空数组
	if len(devices) == 0 {
		c.JSON(200, gin.H{
			"code":    0,
			"message": "success",
			"data":    []AnonymousGroupVO{},
		})
		return
	}

	// 按 group_name 分组统计
	groupMap := make(map[string][]time.Time)
	for _, d := range devices {
		groupMap[d.GroupName] = append(groupMap[d.GroupName], d.LastActiveTime)
	}

	// 预计算时间阈值，避免多次计算
	activeThreshold := time.Now().Add(-5 * time.Minute)

	// 构建结果
	var vos []AnonymousGroupVO
	for groupName, activeTimes := range groupMap {
		var availableCount, disabledCount int64
		for _, activeTime := range activeTimes {
			if activeTime.After(activeThreshold) {
				availableCount++
			} else {
				disabledCount++
			}
		}

		vos = append(vos, AnonymousGroupVO{
			GroupName:        groupName,
			AvailableClients: availableCount,
			DisabledClients:  disabledCount,
			TotalClients:     availableCount + disabledCount,
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
	})
}

// ListOptimized 优化版本：使用数据库聚合查询
func (h *AnonymousGroupHandler) ListOptimized(c *gin.Context) {
	db := database.GetDB()

	// 使用 SQL 直接分组统计
	type GroupStats struct {
		GroupName string  `json:"group_name"`
		Total     int64   `json:"total"`
		ActiveSQL string  `json:"-"` // 用于计算活跃数
	}

	// 查询匿名分组的统计信息
	// 活跃：last_active_time > 5 分钟前
	// 禁用：last_active_time <= 5 分钟前
	activeThreshold := time.Now().Add(-5 * time.Minute)

	var stats []struct {
		GroupName string `json:"group_name"`
		Total     int64  `json:"total"`
		Active    int64  `json:"active"`
		Disabled  int64  `json:"disabled"`
	}

	// 使用 CASE WHEN 在 SQL 层面计算活跃/禁用数量
	if err := db.Table("group_device gd").
		Select(`
			gd.group_name,
			COUNT(*) as total,
			SUM(CASE WHEN gd.last_active_time > ? THEN 1 ELSE 0 END) as active,
			SUM(CASE WHEN gd.last_active_time <= ? THEN 1 ELSE 0 END) as disabled
		`, activeThreshold, activeThreshold).
		Where("NOT EXISTS (SELECT 1 FROM group_config gc WHERE gc.group_name = gd.group_name)").
		Group("gd.group_name").
		Find(&stats).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 如果没有任何匿名设备，直接返回空数组
	if len(stats) == 0 {
		c.JSON(200, gin.H{
			"code":    0,
			"message": "success",
			"data":    []AnonymousGroupVO{},
		})
		return
	}

	// 构建结果
	vos := make([]AnonymousGroupVO, len(stats))
	for i, s := range stats {
		vos[i] = AnonymousGroupVO{
			GroupName:        s.GroupName,
			AvailableClients: s.Active,
			DisabledClients:  s.Disabled,
			TotalClients:     s.Total,
		}
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
	})
}
