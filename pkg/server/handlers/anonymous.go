package handlers

import (
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"time"

	"github.com/gin-gonic/gin"
)

// AnonymousGroupHandler 匿名分组处理器
type AnonymousGroupHandler struct{}

// NewAnonymousGroupHandler 创建匿名分组处理器
func NewAnonymousGroupHandler() *AnonymousGroupHandler {
	return &AnonymousGroupHandler{}
}

// AnonymousGroupVO 匿名分组 VO
type AnonymousGroupVO struct {
	ID               int64  `json:"id"`
	GroupName        string `json:"groupName"`
	AvailableClients int64  `json:"availableClients"`
	DisabledClients  int64  `json:"disabledClients"`
}

// List 获取匿名分组列表
func (h *AnonymousGroupHandler) List(c *gin.Context) {
	// 匿名分组即没有 user_name 的分组
	var groups []model.GroupConfig
	if err := database.GetDB().Where("user_name = '' OR user_name IS NULL").Find(&groups).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	var vos []AnonymousGroupVO
	for _, g := range groups {
		var availableCount, disabledCount int64
		database.GetDB().Model(&model.GroupDevice{}).
			Where("group_name = ? AND last_active_time > ?", g.GroupName, time.Now().Add(-5*time.Minute)).
			Count(&availableCount)
		database.GetDB().Model(&model.GroupDevice{}).
			Where("group_name = ? AND last_active_time <= ?", g.GroupName, time.Now().Add(-5*time.Minute)).
			Count(&disabledCount)

		vos = append(vos, AnonymousGroupVO{
			ID:               g.ID,
			GroupName:        g.GroupName,
			AvailableClients: availableCount,
			DisabledClients:  disabledCount,
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
	})
}
