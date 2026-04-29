package alert

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/smtp"
	"text/template"
	"time"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/model"
	"go.uber.org/zap"
)

var smtpSendMail = smtp.SendMail

// WebhookPayload Webhook 通知载荷
type WebhookPayload struct {
	RuleName     string  `json:"rule_name"`
	RuleID       int64   `json:"rule_id"`
	AlertLevel   string  `json:"alert_level"`
	Group        string  `json:"group,omitempty"`
	API          string  `json:"api,omitempty"`
	MetricName   string  `json:"metric_name"`
	CurrentValue float64 `json:"current_value"`
	Threshold    float64 `json:"threshold"`
	Operator     string  `json:"operator"`
	Message      string  `json:"message"`
	Timestamp    string  `json:"timestamp"`
}

// Notifier 通知发送器接口
type Notifier interface {
	SendWebhook(url string, payload *WebhookPayload) error
	SendEmail(to string, subject string, body string) error
}

// HTTPClient HTTP 客户端接口（用于测试）
type HTTPClient interface {
	Do(req *http.Request) (*http.Response, error)
}

// DefaultHTTPClient 默认 HTTP 客户端
type DefaultHTTPClient struct{}

// Do 执行 HTTP 请求
func (c *DefaultHTTPClient) Do(req *http.Request) (*http.Response, error) {
	return http.DefaultClient.Do(req)
}

// DefaultNotifier 默认通知发送器
type DefaultNotifier struct {
	httpClient HTTPClient
	smtpConfig SMTPConfig
}

// SMTPConfig SMTP 配置
type SMTPConfig struct {
	Host     string
	Port     int
	Username string
	Password string
	From     string
	UseTLS   bool
}

// NewDefaultNotifier 创建默认通知发送器
func NewDefaultNotifier() *DefaultNotifier {
	return &DefaultNotifier{
		httpClient: &DefaultHTTPClient{},
		smtpConfig: SMTPConfig{
			Host:     "localhost",
			Port:     25,
			Username: "",
			Password: "",
			From:     "alert@sekiro.local",
			UseTLS:   false,
		},
	}
}

// SetSMTPConfig 设置 SMTP 配置
func (n *DefaultNotifier) SetSMTPConfig(config SMTPConfig) {
	n.smtpConfig = config
}

// SendWebhook 发送 Webhook 通知
func (n *DefaultNotifier) SendWebhook(url string, payload *WebhookPayload) error {
	if url == "" {
		return fmt.Errorf("webhook URL is empty")
	}

	// 序列化载荷
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %w", err)
	}

	// 创建 HTTP 请求
	req, err := http.NewRequestWithContext(context.Background(), "POST", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	// 设置请求头
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "Sekiro-Alert-Notifier/1.0")

	// 发送请求
	resp, err := n.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send webhook: %w", err)
	}
	defer resp.Body.Close()

	// 检查响应状态
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("webhook returned non-success status: %d", resp.StatusCode)
	}

	logger.Info("Webhook notification sent",
		zap.String("url", url),
		zap.String("rule", payload.RuleName),
		zap.Int("status", resp.StatusCode))

	return nil
}

// SendEmail 发送邮件通知
func (n *DefaultNotifier) SendEmail(to string, subject string, body string) error {
	if to == "" {
		return fmt.Errorf("recipient email is empty")
	}

	// 构建邮件内容
	msg := []byte(fmt.Sprintf("To: %s\r\n"+
		"From: %s\r\n"+
		"Subject: %s\r\n"+
		"Content-Type: text/html; charset=UTF-8\r\n"+
		"\r\n"+
		"%s\r\n", to, n.smtpConfig.From, subject, body))

	// 构建 SMTP 地址
	addr := fmt.Sprintf("%s:%d", n.smtpConfig.Host, n.smtpConfig.Port)

	// 根据是否使用 TLS 选择认证方式
	var err error
	if n.smtpConfig.UseTLS {
		err = n.sendEmailTLS(addr, to, msg)
	} else {
		err = n.sendEmailPlain(addr, to, msg)
	}

	if err != nil {
		return fmt.Errorf("failed to send email: %w", err)
	}

	logger.Info("Email notification sent",
		zap.String("to", to),
		zap.String("subject", subject))

	return nil
}

// sendEmailTLS 使用 TLS 发送邮件
func (n *DefaultNotifier) sendEmailTLS(addr, to string, msg []byte) error {
	auth := smtp.PlainAuth("", n.smtpConfig.Username, n.smtpConfig.Password, n.smtpConfig.Host)
	return smtpSendMail(addr, auth, n.smtpConfig.From, []string{to}, msg)
}

// sendEmailPlain 不使用 TLS 发送邮件
func (n *DefaultNotifier) sendEmailPlain(addr, to string, msg []byte) error {
	return smtpSendMail(addr, nil, n.smtpConfig.From, []string{to}, msg)
}

// BuildEmailBody 构建邮件正文（HTML 格式）
func BuildEmailBody(history *model.AlertHistory) (string, error) {
	tmpl := `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background-color: {{.BgColor}}; color: white; padding: 15px; border-radius: 5px; }
        .content { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .metric { background-color: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 3px; }
        .footer { color: #666; font-size: 12px; margin-top: 20px; }
        table { border-collapse: collapse; width: 100%; }
        td { padding: 8px; }
        .label { font-weight: bold; width: 150px; }
    </style>
</head>
<body>
    <div class="header">
        <h2>🚨 Sekiro 告警通知</h2>
        <p>级别：{{.Level}}</p>
    </div>

    <div class="content">
        <h3>告警详情</h3>
        <table>
            <tr><td class="label">告警规则:</td><td>{{.RuleName}}</td></tr>
            <tr><td class="label">分组:</td><td>{{.Group}}</td></tr>
            <tr><td class="label">API:</td><td>{{.API}}</td></tr>
            <tr><td class="label">指标名称:</td><td>{{.MetricName}}</td></tr>
        </table>

        <h3>指标数据</h3>
        <div class="metric">
            <p><strong>当前值:</strong> {{.CurrentValue}}</p>
            <p><strong>阈值:</strong> {{.Threshold}}</p>
            <p><strong>条件:</strong> {{.CurrentValue}} {{.Operator}} {{.Threshold}}</p>
        </div>

        <p><strong>告警消息:</strong></p>
        <p>{{.Message}}</p>

        <p><strong>触发时间:</strong> {{.TriggeredAt}}</p>
    </div>

    <div class="footer">
        <p>此邮件由 Sekiro 监控系统自动发送，请勿回复。</p>
        <p>如需关闭告警，请访问系统管理页面。</p>
    </div>
</body>
</html>
`

	// 确定告警级别对应的背景色
	bgColor := "#f39c12" // Warning - orange
	switch history.Level {
	case model.AlertLevelInfo:
		bgColor = "#3498db" // Info - blue
	case model.AlertLevelWarning:
		bgColor = "#f39c12" // Warning - orange
	case model.AlertLevelCritical:
		bgColor = "#e74c3c" // Critical - red
	}

	// 格式化触发时间
	triggeredAt := history.TriggeredAt.Format("2006-01-02 15:04:05")

	// 渲染模板
	t, err := template.New("email").Parse(tmpl)
	if err != nil {
		return "", fmt.Errorf("failed to parse email template: %w", err)
	}

	var buf bytes.Buffer
	data := map[string]interface{}{
		"BgColor":      bgColor,
		"Level":        history.Level,
		"RuleName":     history.RuleName,
		"Group":        history.Group,
		"API":          history.API,
		"MetricName":   history.MetricName,
		"CurrentValue": history.CurrentValue,
		"Threshold":    history.Threshold,
		"Operator":     history.Operator,
		"Message":      history.Message,
		"TriggeredAt":  triggeredAt,
	}

	if err := t.Execute(&buf, data); err != nil {
		return "", fmt.Errorf("failed to execute template: %w", err)
	}

	return buf.String(), nil
}

// SendAlertNotification 发送告警通知（统一入口）
func SendAlertNotification(notifier Notifier, rule model.AlertRule, history *model.AlertHistory) error {
	var lastErr error

	// 构建 Webhook 载荷
	payload := &WebhookPayload{
		RuleName:     history.RuleName,
		RuleID:       history.RuleID,
		AlertLevel:   history.Level,
		Group:        history.Group,
		API:          history.API,
		MetricName:   history.MetricName,
		CurrentValue: history.CurrentValue,
		Threshold:    history.Threshold,
		Operator:     history.Operator,
		Message:      history.Message,
		Timestamp:    history.TriggeredAt.Format(time.RFC3339),
	}

	// 发送 Webhook 通知
	if rule.WebhookURL != "" {
		if err := notifier.SendWebhook(rule.WebhookURL, payload); err != nil {
			lastErr = fmt.Errorf("webhook: %w", err)
			logger.Error("Webhook notification failed",
				zap.String("url", rule.WebhookURL),
				zap.Error(err))
		}
	}

	// 发送邮件通知
	if rule.Email != "" {
		emailBody, err := BuildEmailBody(history)
		if err != nil {
			logger.Error("Failed to build email body",
				zap.String("email", rule.Email),
				zap.Error(err))
		} else {
			subject := fmt.Sprintf("[%s] Sekiro 告警：%s", history.Level, history.RuleName)
			if err := notifier.SendEmail(rule.Email, subject, emailBody); err != nil {
				lastErr = fmt.Errorf("email: %w", err)
				logger.Error("Email notification failed",
					zap.String("email", rule.Email),
					zap.Error(err))
			}
		}
	}

	return lastErr
}
