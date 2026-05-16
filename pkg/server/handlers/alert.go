package handlers

import (
	"fmt"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// AlertHandler 告警管理处理器
type AlertHandler struct {
	alertRepo repository.AlertRepository
	evaluator AlertEvaluator
}

// AlertEvaluator 告警评估器接口
type AlertEvaluator interface {
	ReloadRules()
}

// NewAlertHandler 创建告警管理处理器
func NewAlertHandler(alertRepo repository.AlertRepository, evaluator AlertEvaluator) *AlertHandler {
	return &AlertHandler{
		alertRepo: alertRepo,
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
		BadRequest(c, "非法的操作符，应为：>, <, >=, <=, ==, !=")
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
	ID          int64    `json:"id" binding:"required"`
	Name        *string  `json:"name"`
	Description *string  `json:"description"`
	Group       *string  `json:"group"`
	API         *string  `json:"api"`
	MetricName  *string  `json:"metricName"`
	Operator    *string  `json:"operator"`
	Threshold   *float64 `json:"threshold"`
	Window      *int     `json:"window"`
	WebhookURL  *string  `json:"webhookUrl"`
	Email       *string  `json:"email"`
	Enabled     *bool    `json:"enabled"`
}

// GetAlertRules 获取告警规则列表
func (h *AlertHandler) GetAlertRules(c *gin.Context) {
	var query model.AlertRuleQuery
	if err := c.ShouldBindQuery(&query); err != nil {
		BadRequest(c, err.Error())
		return
	}

	rules, total, err := h.alertRepo.FindRulesByQuery(query)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

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

	SuccessWithTotal(c, vos, total)
}

// GetAlertRule 获取告警规则详情
func (h *AlertHandler) GetAlertRule(c *gin.Context) {
	id := c.Param("id")

	var ruleID int64
	if _, err := fmt.Sscanf(id, "%d", &ruleID); err != nil {
		BadRequest(c, "无效的规则 ID")
		return
	}

	rule, err := h.alertRepo.FindRuleByID(ruleID)
	if err != nil || rule == nil {
		NotFound(c, "规则不存在")
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

	Success(c, vo)
}

// CreateAlertRule 创建告警规则
func (h *AlertHandler) CreateAlertRule(c *gin.Context) {
	var req CreateAlertRuleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

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

	if err := h.alertRepo.CreateRule(&rule); err != nil {
		InternalError(c, "创建失败：" + err.Error())
		return
	}

	if h.evaluator != nil {
		h.evaluator.ReloadRules()
	}

	Success(c, rule)
}

// UpdateAlertRule 更新告警规则
func (h *AlertHandler) UpdateAlertRule(c *gin.Context) {
	id := c.Param("id")

	var req UpdateAlertRuleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	if req.Operator != nil && !validateAlertOperator(c, *req.Operator) {
		return
	}

	var ruleID int64
	if _, err := fmt.Sscanf(id, "%d", &ruleID); err != nil {
		BadRequest(c, "无效的规则 ID")
		return
	}

	rule, err := h.alertRepo.FindRuleByID(ruleID)
	if err != nil || rule == nil {
		NotFound(c, "规则不存在")
		return
	}

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

	if err := h.alertRepo.UpdateRule(rule); err != nil {
		InternalError(c, "更新失败：" + err.Error())
		return
	}

	if h.evaluator != nil {
		h.evaluator.ReloadRules()
	}

	Success(c, rule)
}

// DeleteAlertRule 删除告警规则
func (h *AlertHandler) DeleteAlertRule(c *gin.Context) {
	id := c.Param("id")

	var ruleID int64
	if _, err := fmt.Sscanf(id, "%d", &ruleID); err != nil {
		BadRequest(c, "无效的规则 ID")
		return
	}

	if err := h.alertRepo.DeleteRule(ruleID); err != nil {
		InternalError(c, "删除失败：" + err.Error())
		return
	}

	if h.evaluator != nil {
		h.evaluator.ReloadRules()
	}

	Success(c, nil)
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
func (h *AlertHandler) GetAlertHistory(c *gin.Context) {
	var query model.AlertHistoryQuery
	if err := c.ShouldBindQuery(&query); err != nil {
		BadRequest(c, err.Error())
		return
	}

	histories, total, err := h.alertRepo.FindHistoryByQuery(query)
	if err != nil {
		InternalError(c, err.Error())
		return
	}

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

	SuccessWithTotal(c, vos, total)
}
