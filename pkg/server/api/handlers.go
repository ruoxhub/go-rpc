package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/client"
	"github.com/mrh30000/go-rpc/pkg/server/config"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
	"github.com/mrh30000/go-rpc/pkg/server/metrics"
	"github.com/mrh30000/go-rpc/pkg/server/middleware"
	"github.com/mrh30000/go-rpc/pkg/server/router"
	ws "github.com/mrh30000/go-rpc/pkg/server/websocket"
	"gorm.io/gorm"
)

// APIHandler handles HTTP API requests
type APIHandler struct {
	clientManager    clientManagerIface
	router           *router.Router
	wsHandler        *ws.Handler
	timeoutManager   *forwarder.TimeoutManager
	metricsCollector metrics.MetricCollector
	configService    config.Service
}

// clientManagerIface is the interface for client manager (internal)
type clientManagerIface interface {
	GetAllGroups() []string
	GetClientsByGroup(group string) []*client.RpcClient
	AllocateClient(group string) *client.RpcClient
	GetClient(group, clientID string) *client.RpcClient
	GetGroup(groupName string) *client.RpcGroup
}

// RequestBuilder defines the interface for building request data
type RequestBuilder interface {
	BuildRequestData() (action string, params interface{}, err error)
	GetTimeout() time.Duration
	GetSequence(group string) string
	ShouldRecordMetrics() bool
	GetMetricAPI(action string) string
	GetGroup() string
	GetClientID() string
	GetConstantInvoke() string
	GetAccessToken() string
}

// InvokeRequest represents the invoke request body
type InvokeRequest struct {
	Group          string      `json:"group"`
	ClientID       string      `json:"clientId,omitempty"`
	ConstantInvoke string      `json:"constantInvoke,omitempty"`
	RpcToken       string      `json:"sekiro_token,omitempty"`
	Timeout        int         `json:"timeout,omitempty"`
	Action         string      `json:"action"`
	Params         interface{} `json:"params,omitempty"`
}

// ExecJSRequest represents the execjs request body
type ExecJSRequest struct {
	Group          string `json:"group" form:"group"`
	ClientID       string `json:"clientId,omitempty" form:"clientId"`
	ConstantInvoke string `json:"constantInvoke,omitempty" form:"constantInvoke"`
	RpcToken       string `json:"sekiro_token,omitempty" form:"sekiro_token"`
	Code           string `json:"code" form:"code"`
}

// GetCookieRequest represents the getCookie request body
type GetCookieRequest struct {
	Group          string `json:"group" form:"group"`
	ClientID       string `json:"clientId,omitempty" form:"clientId"`
	ConstantInvoke string `json:"constantInvoke,omitempty" form:"constantInvoke"`
	RpcToken       string `json:"sekiro_token,omitempty" form:"sekiro_token"`
}

// NewAPIHandler creates a new APIHandler
func NewAPIHandler(manager *client.ClientManager, wsHandler *ws.Handler, timeoutMgr *forwarder.TimeoutManager, metricsCollector metrics.MetricCollector, cfgSvc config.Service) *APIHandler {
	return &APIHandler{
		clientManager:    manager,
		router:           router.NewRouter(),
		wsHandler:        wsHandler,
		timeoutManager:   timeoutMgr,
		metricsCollector: metricsCollector,
		configService:    cfgSvc,
	}
}

// HandleGroupList handles /business/groupList request
// GET /business/groupList
func (h *APIHandler) HandleGroupList(c *gin.Context) {
	groups := h.clientManager.GetAllGroups()
	logger.Debugf("HandleGroupList: raw groups=%v, count=%d", groups, len(groups))
	filtered, err := h.filterAccessibleGroups(c, groups)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status":  -1,
			"message": err.Error(),
		})
		return
	}
	logger.Debugf("HandleGroupList: filtered groups=%v, count=%d", filtered, len(filtered))
	c.JSON(http.StatusOK, gin.H{
		"status":  0,
		"message": "success",
		"data":    filtered,
	})
}

// HandleClientQueue handles /business/clientQueue request
// GET /business/clientQueue?group=xxx
func (h *APIHandler) HandleClientQueue(c *gin.Context) {
	group := c.Query("group")
	if group == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "group parameter required",
		})
		return
	}
	if !h.authorizeRegisteredGroupAccess(c, group, c.Query("sekiro_token")) {
		return
	}

	clients := h.clientManager.GetClientsByGroup(group)
	clientIDs := make([]string, len(clients))
	for i, c := range clients {
		clientIDs[i] = c.ClientID
	}

	c.JSON(http.StatusOK, gin.H{
		"status":  0,
		"message": "success",
		"data":    clientIDs,
	})
}

// HandleInvoke handles /business/invoke request
// POST/GET /business/invoke
func (h *APIHandler) HandleInvoke(c *gin.Context) {
	startTime := time.Now()
	var req InvokeRequest
	accessToken := resolveAccessToken(c)

	// 根据请求方法绑定数据
	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			// JSON 绑定失败，尝试从查询参数获取
			req.Group = c.Query("group")
			req.ClientID = c.Query("clientId")
			req.ConstantInvoke = c.Query("constantInvoke")
			req.RpcToken = accessToken
			req.Action = c.Query("action")
		}
	} else {
		// GET 方法从查询参数获取
		req.Group = c.Query("group")
		req.ClientID = c.Query("clientId")
		req.ConstantInvoke = c.Query("constantInvoke")
		req.RpcToken = accessToken
		req.Action = c.Query("action")
	}
	if req.RpcToken == "" {
		req.RpcToken = accessToken
	}

	// 参数验证
	if req.Action == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "action parameter required",
		})
		return
	}

	// 使用通用请求处理方法
	builder := &InvokeBuilder{
		Group:          req.Group,
		ClientID:       req.ClientID,
		ConstantInvoke: req.ConstantInvoke,
		AccessToken:    req.RpcToken,
		Action:         req.Action,
		Params:         req.Params,
		Timeout:        time.Duration(req.Timeout) * time.Second,
	}

	h.handleForwardRequest(c, builder, startTime)
}

// marshalJSON is a helper function for JSON marshaling
func marshalJSON(v interface{}) ([]byte, error) {
	return json.Marshal(v)
}

// unmarshalJSON is a helper function for JSON unmarshaling
func unmarshalJSON(data []byte, v interface{}) error {
	return json.Unmarshal(data, v)
}

// HandleExecJS handles /business/execjs request
// POST/GET /business/execjs
func (h *APIHandler) HandleExecJS(c *gin.Context) {
	defer func() {
		if r := recover(); r != nil {
			logger.Errorf("ExecJS handler panic recovered: %v", r)
			c.JSON(http.StatusInternalServerError, gin.H{
				"status":  -1,
				"message": "服务器内部错误",
			})
		}
	}()

	var req ExecJSRequest
	accessToken := resolveAccessToken(c)
	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			req.Group = c.Query("group")
			req.ClientID = c.Query("clientId")
			req.ConstantInvoke = c.Query("constantInvoke")
			req.RpcToken = accessToken
			req.Code = c.Query("code")
		}
	} else {
		req.Group = c.Query("group")
		req.ClientID = c.Query("clientId")
		req.ConstantInvoke = c.Query("constantInvoke")
		req.RpcToken = accessToken
		req.Code = c.Query("code")
	}
	if req.RpcToken == "" {
		req.RpcToken = accessToken
	}

	// 参数验证
	if req.Code == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "code parameter required",
		})
		return
	}

	startTime := time.Now()
	builder := &ExecJSBuilder{
		Group:          req.Group,
		ClientID:       req.ClientID,
		ConstantInvoke: req.ConstantInvoke,
		AccessToken:    req.RpcToken,
		Code:           req.Code,
	}

	h.handleForwardRequest(c, builder, startTime)
}

// HandleGetCookie handles /business/cookie request
// GET /business/cookie
func (h *APIHandler) HandleGetCookie(c *gin.Context) {
	defer func() {
		if r := recover(); r != nil {
			logger.Errorf("GetCookie handler panic recovered: %v", r)
			c.JSON(http.StatusInternalServerError, gin.H{
				"status":  -1,
				"message": "服务器内部错误",
			})
		}
	}()

	var req GetCookieRequest
	accessToken := resolveAccessToken(c)
	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			req.Group = c.Query("group")
			req.ClientID = c.Query("clientId")
			req.ConstantInvoke = c.Query("constantInvoke")
			req.RpcToken = accessToken
		}
	} else {
		req.Group = c.Query("group")
		req.ClientID = c.Query("clientId")
		req.ConstantInvoke = c.Query("constantInvoke")
		req.RpcToken = accessToken
	}
	if req.RpcToken == "" {
		req.RpcToken = accessToken
	}

	startTime := time.Now()
	builder := &GetCookieBuilder{
		Group:          req.Group,
		ClientID:       req.ClientID,
		ConstantInvoke: req.ConstantInvoke,
		AccessToken:    req.RpcToken,
	}

	h.handleForwardRequest(c, builder, startTime)
}

// HandleGetHtml handles /business/html request
// GET /business/html
func (h *APIHandler) HandleGetHtml(c *gin.Context) {
	defer func() {
		if r := recover(); r != nil {
			logger.Errorf("GetHtml handler panic recovered: %v", r)
			c.JSON(http.StatusInternalServerError, gin.H{
				"status":  -1,
				"message": "服务器内部错误",
			})
		}
	}()

	var req GetCookieRequest
	accessToken := resolveAccessToken(c)
	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			req.Group = c.Query("group")
			req.ClientID = c.Query("clientId")
			req.ConstantInvoke = c.Query("constantInvoke")
			req.RpcToken = accessToken
		}
	} else {
		req.Group = c.Query("group")
		req.ClientID = c.Query("clientId")
		req.ConstantInvoke = c.Query("constantInvoke")
		req.RpcToken = accessToken
	}
	if req.RpcToken == "" {
		req.RpcToken = accessToken
	}

	startTime := time.Now()
	builder := &GetHTMLBuilder{
		Group:          req.Group,
		ClientID:       req.ClientID,
		ConstantInvoke: req.ConstantInvoke,
		AccessToken:    req.RpcToken,
	}

	h.handleForwardRequest(c, builder, startTime)
}

func (h *APIHandler) selectTargetClient(groupName, clientID, constantInvoke, action string, payload interface{}) (*client.RpcClient, error) {
	if clientID != "" {
		group := h.clientManager.GetGroup(groupName)
		selected := h.router.Route(group, router.RouteParams{
			GroupName: groupName,
			ClientID:  clientID,
		})
		if selected == nil {
			return nil, fmt.Errorf("client %s not found in group %s", clientID, groupName)
		}
		logger.Infof("Route selected: strategy=specified, group=%s, clientId=%s", groupName, selected.ClientID)
		return selected, nil
	}

	group := h.clientManager.GetGroup(groupName)
	if group == nil {
		return nil, nil
	}

	params := router.RouteParams{GroupName: groupName}
	strategy := "round_robin"
	if shouldUseConsistentHash(constantInvoke) {
		params.HashKey = buildConsistentHashKey(groupName, action, payload)
		strategy = "consistent_hash"
	}

	selected := h.router.Route(group, params)
	if selected == nil {
		return nil, nil
	}

	logger.Infof("Route selected: strategy=%s, group=%s, clientId=%s", strategy, groupName, selected.ClientID)
	return selected, nil
}

func shouldUseConsistentHash(value string) bool {
	if value == "" {
		return false
	}

	enabled, err := strconv.ParseBool(value)
	return err == nil && enabled
}

func buildConsistentHashKey(groupName, action string, payload interface{}) string {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return groupName + ":" + action
	}
	return groupName + ":" + action + ":" + string(encoded)
}

// ==================== Request Builder Implementations ====================

// maxInvokeTimeout is the maximum allowed timeout for invoke requests
const maxInvokeTimeout = 5 * time.Minute

// InvokeBuilder handles standard invoke requests
type InvokeBuilder struct {
	Group          string
	ClientID       string
	ConstantInvoke string
	AccessToken    string
	Action         string
	Params         interface{}
	Timeout        time.Duration
}

func (b *InvokeBuilder) BuildRequestData() (string, interface{}, error) {
	return b.Action, b.Params, nil
}

func (b *InvokeBuilder) GetTimeout() time.Duration {
	if b.Timeout <= 0 {
		return 30 * time.Second
	}
	if b.Timeout > maxInvokeTimeout {
		return maxInvokeTimeout
	}
	return b.Timeout
}

func (b *InvokeBuilder) GetSequence(group string) string {
	return fmt.Sprintf("%s-%s-%d", group, b.Action, time.Now().UnixNano())
}

func (b *InvokeBuilder) ShouldRecordMetrics() bool {
	return true
}

func (b *InvokeBuilder) GetMetricAPI(action string) string {
	return b.Action
}

func (b *InvokeBuilder) GetGroup() string          { return b.Group }
func (b *InvokeBuilder) GetClientID() string       { return b.ClientID }
func (b *InvokeBuilder) GetConstantInvoke() string { return b.ConstantInvoke }
func (b *InvokeBuilder) GetAccessToken() string    { return b.AccessToken }

// ExecJSBuilder handles execjs requests
type ExecJSBuilder struct {
	Group          string
	ClientID       string
	ConstantInvoke string
	AccessToken    string
	Code           string
}

func (b *ExecJSBuilder) BuildRequestData() (string, interface{}, error) {
	return "_execjs", b.Code, nil
}

func (b *ExecJSBuilder) GetTimeout() time.Duration {
	return 30 * time.Second
}

func (b *ExecJSBuilder) GetSequence(group string) string {
	return fmt.Sprintf("%s-_execjs-%d", group, time.Now().UnixNano())
}

func (b *ExecJSBuilder) ShouldRecordMetrics() bool {
	return false
}

func (b *ExecJSBuilder) GetMetricAPI(action string) string {
	return action
}

func (b *ExecJSBuilder) GetGroup() string          { return b.Group }
func (b *ExecJSBuilder) GetClientID() string       { return b.ClientID }
func (b *ExecJSBuilder) GetConstantInvoke() string { return b.ConstantInvoke }
func (b *ExecJSBuilder) GetAccessToken() string    { return b.AccessToken }

// GetCookieBuilder handles cookie requests
type GetCookieBuilder struct {
	Group          string
	ClientID       string
	ConstantInvoke string
	AccessToken    string
}

func (b *GetCookieBuilder) BuildRequestData() (string, interface{}, error) {
	return "_execjs", "document.cookie", nil
}

func (b *GetCookieBuilder) GetTimeout() time.Duration {
	return 30 * time.Second
}

func (b *GetCookieBuilder) GetSequence(group string) string {
	return fmt.Sprintf("%s-_cookie-%d", group, time.Now().UnixNano())
}

func (b *GetCookieBuilder) ShouldRecordMetrics() bool {
	return false
}

func (b *GetCookieBuilder) GetMetricAPI(action string) string {
	return action
}

func (b *GetCookieBuilder) GetGroup() string          { return b.Group }
func (b *GetCookieBuilder) GetClientID() string       { return b.ClientID }
func (b *GetCookieBuilder) GetConstantInvoke() string { return b.ConstantInvoke }
func (b *GetCookieBuilder) GetAccessToken() string    { return b.AccessToken }

// GetHTMLBuilder handles html requests
type GetHTMLBuilder struct {
	Group          string
	ClientID       string
	ConstantInvoke string
	AccessToken    string
}

func (b *GetHTMLBuilder) BuildRequestData() (string, interface{}, error) {
	return "_execjs", "document.documentElement.outerHTML", nil
}

func (b *GetHTMLBuilder) GetTimeout() time.Duration {
	return 30 * time.Second
}

func (b *GetHTMLBuilder) GetSequence(group string) string {
	return fmt.Sprintf("%s-_html-%d", group, time.Now().UnixNano())
}

func (b *GetHTMLBuilder) ShouldRecordMetrics() bool {
	return false
}

func (b *GetHTMLBuilder) GetMetricAPI(action string) string {
	return action
}

func (b *GetHTMLBuilder) GetGroup() string          { return b.Group }
func (b *GetHTMLBuilder) GetClientID() string       { return b.ClientID }
func (b *GetHTMLBuilder) GetConstantInvoke() string { return b.ConstantInvoke }
func (b *GetHTMLBuilder) GetAccessToken() string    { return b.AccessToken }

// handleForwardRequest is the generic handler for forwarding requests to Rpc clients
func (h *APIHandler) handleForwardRequest(c *gin.Context, builder RequestBuilder, startTime time.Time) {
	// 从 builder 获取参数（已由具体 handler 绑定）
	group := builder.GetGroup()
	clientID := builder.GetClientID()
	constantInvoke := builder.GetConstantInvoke()

	// 获取 action 用于日志
	action, _, _ := builder.BuildRequestData()
	logger.Infof("Request: group=%s, clientId=%s, action=%s", group, clientID, action)

	// 参数验证
	if group == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "group parameter required",
		})
		return
	}
	if !h.authorizeRegisteredGroupAccess(c, group, builder.GetAccessToken()) {
		return
	}

	// 空转调用保护检查（仅 Invoke 需要）
	if builder.ShouldRecordMetrics() && h.configService != nil && h.configService.GetConfigBool(config.ConfigKeyDefendIdleInvoke, true) {
		if constantInvoke == "true" || constantInvoke == "1" {
			logger.Warnf("DefendIdleInvoke: blocked constant invoke request, group=%s, action=%s", group, action)
			c.JSON(http.StatusOK, gin.H{
				"status":  -1,
				"message": "空转调用被拒绝，请联系管理员配置实际处理逻辑",
			})
			return
		}
	}

	// 构建请求数据
	reqAction, reqParams, err := builder.BuildRequestData()
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Failed to build request data: " + err.Error(),
		})
		return
	}

	// 分配客户端
	targetClient, err := h.selectTargetClient(group, clientID, constantInvoke, reqAction, reqParams)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": err.Error(),
		})
		return
	}

	if targetClient == nil {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "no client available",
		})
		return
	}

	// 构建 Rpc 请求数据
	reqData := map[string]interface{}{
		"action": reqAction,
		"params": reqParams,
	}

	reqDataJSON, err := marshalJSON(reqData)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Failed to marshal request data: " + err.Error(),
		})
		return
	}

	// 生成唯一的 sequence ID
	sequence := builder.GetSequence(group)

	// 创建 invoke 记录
	timeout := builder.GetTimeout()
	invokeRecord := h.timeoutManager.Add(sequence, group, targetClient.ClientID, reqDataJSON)
	invokeRecord.Timeout = timeout

	// 获取 WebSocket 连接并发送请求
	conn, ok := targetClient.Connection.(*websocket.Conn)
	if !ok {
		h.timeoutManager.Remove(sequence)
		c.JSON(http.StatusOK, gin.H{
			"status":   -1,
			"message":  "Invalid client connection",
			"group":    group,
			"clientId": targetClient.ClientID,
		})
		return
	}

	// 发送 invoke 请求
	err = h.wsHandler.SendInvokeRequest(conn, sequence, group, targetClient.ClientID, reqDataJSON, targetClient)
	if err != nil {
		h.timeoutManager.Remove(sequence)
		targetClient.MarkFailure()
		c.JSON(http.StatusOK, gin.H{
			"status":   -1,
			"message":  "Failed to send request: " + err.Error(),
			"group":    group,
			"clientId": targetClient.ClientID,
		})
		return
	}

	logger.Infof("Request sent: sequence=%s, group=%s, clientId=%s", sequence, group, targetClient.ClientID)

	// 等待响应
	ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
	defer cancel()

	responseChan := make(chan *forwarder.InvokeResponse, 1)
	go func() {
		resp, err := h.timeoutManager.Wait(sequence)
		if err != nil {
			responseChan <- &forwarder.InvokeResponse{
				Error:  err.Error(),
				Status: -1,
			}
		} else {
			responseChan <- resp
		}
	}()

	select {
	case <-ctx.Done():
		h.timeoutManager.Remove(sequence)
		targetClient.MarkFailure()
		// 记录超时指标
		if builder.ShouldRecordMetrics() && h.metricsCollector != nil {
			metricAPI := builder.GetMetricAPI(reqAction)
			h.metricsCollector.Incr("invoke.total", map[string]string{"group": group, "api": metricAPI, "status": "timeout"}, 1)
			h.metricsCollector.RecordLatency("invoke.latency", map[string]string{"group": group, "api": metricAPI}, float64(time.Since(startTime).Milliseconds()))
		}
		c.JSON(http.StatusOK, gin.H{
			"status":   -1,
			"message":  "Request timeout",
			"group":    group,
			"clientId": targetClient.ClientID,
		})
		return
	case resp := <-responseChan:
		// Mark client health based on response
		if resp.Status >= 0 && resp.Error == "" {
			targetClient.MarkSuccess()
		} else {
			targetClient.MarkFailure()
		}

		// 记录调用指标
		if builder.ShouldRecordMetrics() && h.metricsCollector != nil {
			status := "success"
			if resp.Status < 0 || resp.Error != "" {
				status = "failure"
			}
			metricAPI := builder.GetMetricAPI(reqAction)
			h.metricsCollector.Incr("invoke.total", map[string]string{"group": group, "api": metricAPI, "status": status}, 1)
			h.metricsCollector.RecordLatency("invoke.latency", map[string]string{"group": group, "api": metricAPI}, float64(time.Since(startTime).Milliseconds()))
		}

		if resp.Error != "" {
			c.JSON(http.StatusOK, gin.H{
				"status":   resp.Status,
				"message":  resp.Error,
				"group":    group,
				"clientId": targetClient.ClientID,
			})
			return
		}

		// 如果 status 为 -1 但没有 Error，说明是异常情况
		message := "success"
		if resp.Status < 0 {
			message = "unknown error"
		}

		// 解析响应数据，如果是 JSON object 则平级展开
		var responseMap map[string]interface{}
		if err := unmarshalJSON(resp.Data, &responseMap); err == nil {
			result := gin.H{
				"status":   resp.Status,
				"message":  message,
				"group":    group,
				"clientId": targetClient.ClientID,
			}
			for k, v := range responseMap {
				result[k] = v
			}
			c.JSON(http.StatusOK, result)
			return
		}

		// 如果响应不是有效 JSON，当作字符串处理
		c.JSON(http.StatusOK, gin.H{
			"status":   resp.Status,
			"message":  message,
			"group":    group,
			"clientId": targetClient.ClientID,
			"data":     string(resp.Data),
		})
	}
}

func (h *APIHandler) authorizeRegisteredGroupAccess(c *gin.Context, groupName, token string) bool {
	db := database.GetDB()
	if db == nil {
		return true
	}

	var group model.GroupConfig
	if err := db.Where("group_name = ?", groupName).First(&group).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return true
		}
		c.JSON(http.StatusInternalServerError, gin.H{
			"status":  -1,
			"message": "failed to verify group access: " + err.Error(),
		})
		return false
	}

	if token == "" {
		token = middleware.ExtractAuthTokenFromRequest(c)
	}
	user, err := middleware.FindUserByToken(token)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{
			"status":  -1,
			"message": "registered group requires a valid sekiro token",
		})
		return false
	}

	if !user.IsAdmin && user.UserName != group.UserName {
		c.JSON(http.StatusForbidden, gin.H{
			"status":  -1,
			"message": "no access to registered group",
		})
		return false
	}

	c.Set(middleware.ContextUserKey, user)
	return true
}

func (h *APIHandler) filterAccessibleGroups(c *gin.Context, groups []string) ([]string, error) {
	db := database.GetDB()
	if db == nil {
		return groups, nil
	}

	token := middleware.ExtractAuthTokenFromRequest(c)
	var user *model.UserInfo
	if token != "" {
		resolved, err := middleware.FindUserByToken(token)
		if err == nil {
			user = resolved
			c.Set(middleware.ContextUserKey, user)
		}
	}

	filtered := make([]string, 0, len(groups))
	for _, groupName := range groups {
		var group model.GroupConfig
		err := db.Where("group_name = ?", groupName).First(&group).Error
		if err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				filtered = append(filtered, groupName)
				continue
			}
			// 数据库查询异常时保守处理：视为匿名分组并保留，避免临时故障导致 groupList 完全不可用
			logger.Warnf("filterAccessibleGroups: query group_config failed for %s: %v, treating as anonymous", groupName, err)
			filtered = append(filtered, groupName)
			continue
		}

		if user != nil && (user.IsAdmin || user.UserName == group.UserName) {
			filtered = append(filtered, groupName)
		}
	}

	return filtered, nil
}

func resolveAccessToken(c *gin.Context) string {
	return middleware.ExtractAuthTokenFromRequest(c)
}
