package handlers

import (
	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
)

// AlertHandler 告警管理处理器
type AlertHandler struct {
	evaluator AlertEvaluator
}

// AlertEvaluator 告警评估器接口
type AlertEvaluator interface {
	ReloadRules()
}

// NewAlertHandler 创建告警管理处理器
func NewAlertHandler(evaluator AlertEvaluator) *AlertHandler {
	return &AlertHandler{
		evaluator: evaluator,
	}
}

// isValidOperator 验证操作符是否合法
func isValidOperator(op string) bool {
	switch op {
	case model.OpGreaterThan, model.OpLessThan, model.OpGreaterThanOrEqual,
		model.OpLessThanOrEqual, model.OpEqual, model.OpNotEqual:
		return true
	default:
		return false
	}
}

// validateAlertOperator 验证告警操作符
func validateAlertOperator(c *gin.Context, op string) bool {
	if !isValidOperator(op) {
		c.JSON(400, gin.H{
			"code":    400,
			"message": "非法的操作符，应为：>, <, >=, <=, ==, !=",
		})
		return false
	}
	return true
}

// AlertRuleVO 告警规则 VO
type AlertRuleVO struct {
	ID          int64   `json:"id"`
	Name        string  `json:"name"`
	Description string  `json:"description"`
	Group       string  `json:"group"`
	API         string  `json:"api"`
	MetricName  string  `json:"metricName"`
	Operator    string  `json:"operator"`
	Threshold   float64 `json:"threshold"`
	Window      int     `json:"window"`
	WebhookURL  string  `json:"webhookUrl"`
	Email       string  `json:"email"`
	Enabled     bool    `json:"enabled"`
	CreatedAt   string  `json:"createdAt"`
	UpdatedAt   string  `json:"updatedAt"`
}

// CreateAlertRuleRequest 创建告警规则请求
type CreateAlertRuleRequest struct {
	Name        string  `json:"name" binding:"required"`
	Description string  `json:"description"`
	Group       string  `json:"group"`
	API         string  `json:"api"`
	MetricName  string  `json:"metricName" binding:"required"`
	Operator    string  `json:"operator" binding:"required"`
	Threshold   float64 `json:"threshold" binding:"required"`
	Window      int     `json:"window" binding:"required"`
	WebhookURL  string  `json:"webhookUrl"`
	Email       string  `json:"email"`
	Enabled     bool    `json:"enabled"`
}

// UpdateAlertRuleRequest 更新告警规则请求
type UpdateAlertRuleRequest struct {
	ID          int64   `json:"id" binding:"required"`
	Name        *string `json:"name"`
	Description *string `json:"description"`
	Group       *string `json:"group"`
	API         *string `json:"api"`
	MetricName  *string `json:"metricName"`
	Operator    *string `json:"operator"`
	Threshold   *float64 `json:"threshold"`
	Window      *int    `json:"window"`
	WebhookURL  *string `json:"webhookUrl"`
	Email       *string `json:"email"`
	Enabled     *bool   `json:"enabled"`
}

// GetAlertRules 获取告警规则列表
// GET /api/alerts/rules
func (h *AlertHandler) GetAlertRules(c *gin.Context) {
	var query model.AlertRuleQuery
	if err := c.ShouldBindQuery(&query); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 构建查询
	dbQuery := database.GetDB().Table("alert_rule")

	if query.Group != "" {
		dbQuery = dbQuery.Where("\"group\" = ?", query.Group)
	}
	if query.Enabled != nil {
		dbQuery = dbQuery.Where("enabled = ?", *query.Enabled)
	}

	// 获取总数
	var total int64
	dbQuery.Count(&total)

	// 分页
	offset := (query.Page - 1) * query.PageSize
	dbQuery = dbQuery.Offset(offset).Limit(query.PageSize).Order("created_at DESC")

	var rules []model.AlertRule
	if err := dbQuery.Find(&rules).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 转换为 VO
	var vos []AlertRuleVO
	for _, rule := range rules {
		vos = append(vos, AlertRuleVO{
			ID:          rule.ID,
			Name:        rule.Name,
			Description: rule.Description,
			Group:       rule.Group,
			API:         rule.API,
			MetricName:  rule.MetricName,
			Operator:    rule.Operator,
			Threshold:   rule.Threshold,
			Window:      rule.Window,
			WebhookURL:  rule.WebhookURL,
			Email:       rule.Email,
			Enabled:     rule.Enabled,
			CreatedAt:   rule.CreatedAt.Format("2006-01-02 15:04:05"),
			UpdatedAt:   rule.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
		"total":   total,
	})
}

// GetAlertRule 获取告警规则详情
// GET /api/alerts/rules/:id
func (h *AlertHandler) GetAlertRule(c *gin.Context) {
	id := c.Param("id")

	var rule model.AlertRule
	if err := database.GetDB().First(&rule, id).Error; err != nil {
		c.JSON(404, gin.H{"code": 404, "message": "规则不存在"})
		return
	}

	vo := AlertRuleVO{
		ID:          rule.ID,
		Name:        rule.Name,
		Description: rule.Description,
		Group:       rule.Group,
		API:         rule.API,
		MetricName:  rule.MetricName,
		Operator:    rule.Operator,
		Threshold:   rule.Threshold,
		Window:      rule.Window,
		WebhookURL:  rule.WebhookURL,
		Email:       rule.Email,
		Enabled:     rule.Enabled,
		CreatedAt:   rule.CreatedAt.Format("2006-01-02 15:04:05"),
		UpdatedAt:   rule.UpdatedAt.Format("2006-01-02 15:04:05"),
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vo,
	})
}

// CreateAlertRule 创建告警规则
// POST /api/alerts/rules
func (h *AlertHandler) CreateAlertRule(c *gin.Context) {
	var req CreateAlertRuleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 验证操作符
	if !validateAlertOperator(c, req.Operator) {
		return
	}

	rule := model.AlertRule{
		Name:        req.Name,
		Description: req.Description,
		Group:       req.Group,
		API:         req.API,
		MetricName:  req.MetricName,
		Operator:    req.Operator,
		Threshold:   req.Threshold,
		Window:      req.Window,
		WebhookURL:  req.WebhookURL,
		Email:       req.Email,
		Enabled:     req.Enabled,
	}

	if err := database.GetDB().Create(&rule).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": "创建失败：" + err.Error()})
		return
	}

	// 重新加载规则
	if h.evaluator != nil {
		h.evaluator.ReloadRules()
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    rule,
	})
}

// UpdateAlertRule 更新告警规则
// PUT /api/alerts/rules/:id
func (h *AlertHandler) UpdateAlertRule(c *gin.Context) {
	id := c.Param("id")

	var req UpdateAlertRuleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 验证操作符（如果提供了）
	if req.Operator != nil && !validateAlertOperator(c, *req.Operator) {
		return
	}

	var rule model.AlertRule
	if err := database.GetDB().First(&rule, id).Error; err != nil {
		c.JSON(404, gin.H{"code": 404, "message": "规则不存在"})
		return
	}

	// 更新字段（指针字段允许清空）
	if req.Name != nil {
		rule.Name = *req.Name
	}
	if req.Description != nil {
		rule.Description = *req.Description
	}
	if req.Group != nil {
		rule.Group = *req.Group
	}
	if req.API != nil {
		rule.API = *req.API
	}
	if req.MetricName != nil {
		rule.MetricName = *req.MetricName
	}
	if req.Operator != nil {
		rule.Operator = *req.Operator
	}
	if req.Threshold != nil {
		rule.Threshold = *req.Threshold
	}
	if req.Window != nil {
		rule.Window = *req.Window
	}
	if req.WebhookURL != nil {
		rule.WebhookURL = *req.WebhookURL
	}
	if req.Email != nil {
		rule.Email = *req.Email
	}
	if req.Enabled != nil {
		rule.Enabled = *req.Enabled
	}

	if err := database.GetDB().Save(&rule).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": "更新失败：" + err.Error()})
		return
	}

	// 重新加载规则
	if h.evaluator != nil {
		h.evaluator.ReloadRules()
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    rule,
	})
}

// DeleteAlertRule 删除告警规则
// DELETE /api/alerts/rules/:id
func (h *AlertHandler) DeleteAlertRule(c *gin.Context) {
	id := c.Param("id")

	var rule model.AlertRule
	if err := database.GetDB().First(&rule, id).Error; err != nil {
		c.JSON(404, gin.H{"code": 404, "message": "规则不存在"})
		return
	}

	if err := database.GetDB().Delete(&rule).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": "删除失败：" + err.Error()})
		return
	}

	// 重新加载规则
	if h.evaluator != nil {
		h.evaluator.ReloadRules()
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
	})
}

// AlertHistoryVO 告警历史 VO
type AlertHistoryVO struct {
	ID           int64   `json:"id"`
	RuleID       int64   `json:"ruleId"`
	RuleName     string  `json:"ruleName"`
	Group        string  `json:"group"`
	API          string  `json:"api"`
	MetricName   string  `json:"metricName"`
	CurrentValue float64 `json:"currentValue"`
	Threshold    float64 `json:"threshold"`
	Operator     string  `json:"operator"`
	Level        string  `json:"level"`
	Notified     bool    `json:"notified"`
	NotifyError  string  `json:"notifyError"`
	TriggeredAt  string  `json:"triggeredAt"`
	Message      string  `json:"message"`
}

// GetAlertHistory 获取告警历史
// GET /api/alerts/history
func (h *AlertHandler) GetAlertHistory(c *gin.Context) {
	var query model.AlertHistoryQuery
	if err := c.ShouldBindQuery(&query); err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}

	// 构建查询
	dbQuery := database.GetDB().Table("alert_history")

	if query.RuleID > 0 {
		dbQuery = dbQuery.Where("rule_id = ?", query.RuleID)
	}
	if query.Group != "" {
		dbQuery = dbQuery.Where("\"group\" = ?", query.Group)
	}
	if query.Level != "" {
		dbQuery = dbQuery.Where("level = ?", query.Level)
	}
	if query.StartTime != "" {
		dbQuery = dbQuery.Where("triggered_at >= ?", query.StartTime)
	}
	if query.EndTime != "" {
		dbQuery = dbQuery.Where("triggered_at <= ?", query.EndTime)
	}

	// 获取总数
	var total int64
	dbQuery.Count(&total)

	// 分页
	offset := (query.Page - 1) * query.PageSize
	dbQuery = dbQuery.Offset(offset).Limit(query.PageSize).Order("triggered_at DESC")

	var histories []model.AlertHistory
	if err := dbQuery.Find(&histories).Error; err != nil {
		c.JSON(500, gin.H{"code": 500, "message": err.Error()})
		return
	}

	// 转换为 VO
	var vos []AlertHistoryVO
	for _, h := range histories {
		vos = append(vos, AlertHistoryVO{
			ID:           h.ID,
			RuleID:       h.RuleID,
			RuleName:     h.RuleName,
			Group:        h.Group,
			API:          h.API,
			MetricName:   h.MetricName,
			CurrentValue: h.CurrentValue,
			Threshold:    h.Threshold,
			Operator:     h.Operator,
			Level:        h.Level,
			Notified:     h.Notified,
			NotifyError:  h.NotifyError,
			TriggeredAt:  h.TriggeredAt.Format("2006-01-02 15:04:05"),
			Message:      h.Message,
		})
	}

	c.JSON(200, gin.H{
		"code":    0,
		"message": "success",
		"data":    vos,
		"total":   total,
	})
}
