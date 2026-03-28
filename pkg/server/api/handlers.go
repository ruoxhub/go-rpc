package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/server/client"
	"github.com/sekiro-go/sekiro-go/pkg/server/forwarder"
	"github.com/sekiro-go/sekiro-go/pkg/server/metrics"
	"github.com/sekiro-go/sekiro-go/pkg/server/router"
	ws "github.com/sekiro-go/sekiro-go/pkg/server/websocket"
)

// APIHandler handles HTTP API requests
type APIHandler struct {
	clientManager    clientManagerIface
	router           *router.Router
	wsHandler        *ws.Handler
	timeoutManager   *forwarder.TimeoutManager
	metricsCollector metrics.MetricCollector
}

// clientManagerIface is the interface for client manager (internal)
type clientManagerIface interface {
	GetAllGroups() []string
	GetClientsByGroup(group string) []*client.SekiroClient
	AllocateClient(group string) *client.SekiroClient
	GetClient(group, clientID string) *client.SekiroClient
	GetGroup(groupName string) *client.SekiroGroup
}

// InvokeRequest represents the invoke request body
type InvokeRequest struct {
	Group          string      `json:"group"`
	ClientID       string      `json:"clientId,omitempty"`
	ConstantInvoke string      `json:"constantInvoke,omitempty"`
	Timeout        int         `json:"timeout,omitempty"`
	Action         string      `json:"action"`
	Params         interface{} `json:"params,omitempty"`
}

// ExecJSRequest represents the execjs request body
type ExecJSRequest struct {
	Group          string `json:"group" form:"group"`
	ClientID       string `json:"clientId,omitempty" form:"clientId"`
	ConstantInvoke string `json:"constantInvoke,omitempty" form:"constantInvoke"`
	Code           string `json:"code" form:"code"`
}

// GetCookieRequest represents the getCookie request body
type GetCookieRequest struct {
	Group          string `json:"group" form:"group"`
	ClientID       string `json:"clientId,omitempty" form:"clientId"`
	ConstantInvoke string `json:"constantInvoke,omitempty" form:"constantInvoke"`
}

// NewAPIHandler creates a new APIHandler
func NewAPIHandler(manager *client.ClientManager, wsHandler *ws.Handler, timeoutMgr *forwarder.TimeoutManager, metricsCollector metrics.MetricCollector) *APIHandler {
	return &APIHandler{
		clientManager:    manager,
		router:           router.NewRouter(),
		wsHandler:        wsHandler,
		timeoutManager:   timeoutMgr,
		metricsCollector: metricsCollector,
	}
}

// HandleGroupList handles /business/groupList request
// GET /business/groupList
func (h *APIHandler) HandleGroupList(c *gin.Context) {
	groups := h.clientManager.GetAllGroups()
	c.JSON(http.StatusOK, gin.H{
		"status":  0,
		"message": "success",
		"data":    groups,
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
	startTime := time.Now() // 记录开始时间用于延迟统计
	var req InvokeRequest

	// 根据请求方法绑定数据
	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			// JSON 绑定失败，尝试从查询参数获取
			req.Group = c.Query("group")
			req.ClientID = c.Query("clientId")
			req.ConstantInvoke = c.Query("constantInvoke")
			req.Action = c.Query("action")
		}
	} else {
		// GET 方法从查询参数获取
		req.Group = c.Query("group")
		req.ClientID = c.Query("clientId")
		req.ConstantInvoke = c.Query("constantInvoke")
		req.Action = c.Query("action")
	}

	logger.Infof("Invoke request: group=%s, clientId=%s, action=%s", req.Group, req.ClientID, req.Action)

	// 参数验证
	if req.Group == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "group parameter required",
		})
		return
	}

	if req.Action == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "action parameter required",
		})
		return
	}

	// 分配客户端
	var targetClient *client.SekiroClient
	targetClient, err := h.selectTargetClient(req.Group, req.ClientID, req.ConstantInvoke, req.Action, req.Params)
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

	// 构建 Sekiro 请求数据
	reqData := map[string]interface{}{
		"action": req.Action,
		"params": req.Params,
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
	sequence := fmt.Sprintf("%s-%s-%d", req.Group, req.Action, time.Now().UnixNano())

	// 创建 invoke 记录
	timeout := time.Duration(req.Timeout) * time.Second
	if timeout <= 0 {
		timeout = 30 * time.Second // 默认 30 秒超时
	}
	invokeRecord := h.timeoutManager.Add(sequence, req.Group, targetClient.ClientID, reqDataJSON)
	invokeRecord.Timeout = timeout

	// 获取 WebSocket 连接并发送请求
	conn, ok := targetClient.Connection.(*websocket.Conn)
	if !ok {
		h.timeoutManager.Remove(sequence)
		c.JSON(http.StatusOK, gin.H{
			"status":   -1,
			"message":  "Invalid client connection",
			"group":    req.Group,
			"clientId": targetClient.ClientID,
		})
		return
	}

	// 发送 invoke 请求
	err = h.wsHandler.SendInvokeRequest(conn, sequence, req.Group, targetClient.ClientID, reqDataJSON)
	if err != nil {
		h.timeoutManager.Remove(sequence)
		// Mark client failure on send error
		targetClient.MarkFailure()
		c.JSON(http.StatusOK, gin.H{
			"status":   -1,
			"message":  "Failed to send request: " + err.Error(),
			"group":    req.Group,
			"clientId": targetClient.ClientID,
		})
		return
	}

	logger.Infof("Invoke request sent: sequence=%s, group=%s, clientId=%s", sequence, req.Group, targetClient.ClientID)

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
		// Mark client failure on timeout
		targetClient.MarkFailure()
		// 记录超时指标
		if h.metricsCollector != nil {
			h.metricsCollector.Incr("invoke.total", map[string]string{"group": req.Group, "api": req.Action, "status": "timeout"}, 1)
			h.metricsCollector.RecordLatency("invoke.latency", map[string]string{"group": req.Group, "api": req.Action}, float64(time.Since(startTime).Milliseconds()))
		}
		c.JSON(http.StatusOK, gin.H{
			"status":   -1,
			"message":  "Request timeout",
			"group":    req.Group,
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
		if h.metricsCollector != nil {
			status := "success"
			if resp.Status < 0 || resp.Error != "" {
				status = "failure"
			}
			h.metricsCollector.Incr("invoke.total", map[string]string{"group": req.Group, "api": req.Action, "status": status}, 1)
			h.metricsCollector.RecordLatency("invoke.latency", map[string]string{"group": req.Group, "api": req.Action}, float64(time.Since(startTime).Milliseconds()))
		}

		if resp.Error != "" {
			c.JSON(http.StatusOK, gin.H{
				"status":   resp.Status,
				"message":  resp.Error,
				"group":    req.Group,
				"clientId": targetClient.ClientID,
			})
			return
		}

		// 解析响应数据
		var responseData interface{}
		if err := unmarshalJSON(resp.Data, &responseData); err != nil {
			// 如果响应不是有效 JSON，当作字符串处理
			responseData = string(resp.Data)
		}

		// 如果 status 为 -1 但没有 Error，说明是异常情况
		message := "success"
		if resp.Status < 0 {
			message = "unknown error"
		}

		c.JSON(http.StatusOK, gin.H{
			"status":   resp.Status,
			"message":  message,
			"group":    req.Group,
			"clientId": targetClient.ClientID,
			"data":     responseData,
		})
	}
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
	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			req.Group = c.Query("group")
			req.ClientID = c.Query("clientId")
			req.ConstantInvoke = c.Query("constantInvoke")
			req.Code = c.Query("code")
		}
	} else {
		req.Group = c.Query("group")
		req.ClientID = c.Query("clientId")
		req.ConstantInvoke = c.Query("constantInvoke")
		req.Code = c.Query("code")
	}

	logger.Infof("ExecJS request: group=%s, clientId=%s", req.Group, req.ClientID)

	// 参数验证
	if req.Group == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "group parameter required",
		})
		return
	}

	if req.Code == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "code parameter required",
		})
		return
	}

	// 分配客户端
	var targetClient *client.SekiroClient
	targetClient, err := h.selectTargetClient(req.Group, req.ClientID, req.ConstantInvoke, "_execjs", req.Code)
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

	// 构建 Sekiro 请求数据 - 使用_execjs action
	reqData := map[string]interface{}{
		"action": "_execjs",
		"params": req.Code,
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
	sequence := fmt.Sprintf("%s-_execjs-%d", req.Group, time.Now().UnixNano())

	// 创建 invoke 记录
	timeout := 30 * time.Second // 默认 30 秒超时
	invokeRecord := h.timeoutManager.Add(sequence, req.Group, targetClient.ClientID, reqDataJSON)
	invokeRecord.Timeout = timeout

	// 获取 WebSocket 连接并发送请求
	conn, ok := targetClient.Connection.(*websocket.Conn)
	if !ok {
		h.timeoutManager.Remove(sequence)
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Invalid client connection",
		})
		return
	}

	// 发送 invoke 请求
	err = h.wsHandler.SendInvokeRequest(conn, sequence, req.Group, targetClient.ClientID, reqDataJSON)
	if err != nil {
		h.timeoutManager.Remove(sequence)
		targetClient.MarkFailure()
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Failed to send request: " + err.Error(),
		})
		return
	}

	logger.Infof("ExecJS request sent: sequence=%s, group=%s, clientId=%s", sequence, req.Group, targetClient.ClientID)

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
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Request timeout",
		})
		return
	case resp := <-responseChan:
		if resp.Status >= 0 && resp.Error == "" {
			targetClient.MarkSuccess()
		} else {
			targetClient.MarkFailure()
		}

		if resp.Error != "" {
			c.JSON(http.StatusOK, gin.H{
				"status":  resp.Status,
				"message": resp.Error,
			})
			return
		}

		// 解析响应数据
		var responseData interface{}
		if err := unmarshalJSON(resp.Data, &responseData); err != nil {
			responseData = string(resp.Data)
		}

		c.JSON(http.StatusOK, gin.H{
			"status":   resp.Status,
			"message":  "success",
			"group":    req.Group,
			"clientId": targetClient.ClientID,
			"data":     responseData,
		})
	}
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
	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			req.Group = c.Query("group")
			req.ClientID = c.Query("clientId")
			req.ConstantInvoke = c.Query("constantInvoke")
		}
	} else {
		req.Group = c.Query("group")
		req.ClientID = c.Query("clientId")
		req.ConstantInvoke = c.Query("constantInvoke")
	}

	logger.Infof("GetCookie request: group=%s, clientId=%s", req.Group, req.ClientID)

	// 参数验证
	if req.Group == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "group parameter required",
		})
		return
	}

	// 分配客户端
	var targetClient *client.SekiroClient
	targetClient, err := h.selectTargetClient(req.Group, req.ClientID, req.ConstantInvoke, "_execjs", "document.cookie")
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

	// 构建 Sekiro 请求数据 - 执行 document.cookie
	reqData := map[string]interface{}{
		"action": "_execjs",
		"params": "document.cookie",
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
	sequence := fmt.Sprintf("%s-_cookie-%d", req.Group, time.Now().UnixNano())

	// 创建 invoke 记录
	timeout := 30 * time.Second // 默认 30 秒超时
	invokeRecord := h.timeoutManager.Add(sequence, req.Group, targetClient.ClientID, reqDataJSON)
	invokeRecord.Timeout = timeout

	// 获取 WebSocket 连接并发送请求
	conn, ok := targetClient.Connection.(*websocket.Conn)
	if !ok {
		h.timeoutManager.Remove(sequence)
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Invalid client connection",
		})
		return
	}

	// 发送 invoke 请求
	err = h.wsHandler.SendInvokeRequest(conn, sequence, req.Group, targetClient.ClientID, reqDataJSON)
	if err != nil {
		h.timeoutManager.Remove(sequence)
		targetClient.MarkFailure()
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Failed to send request: " + err.Error(),
		})
		return
	}

	logger.Infof("GetCookie request sent: sequence=%s, group=%s, clientId=%s", sequence, req.Group, targetClient.ClientID)

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
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Request timeout",
		})
		return
	case resp := <-responseChan:
		if resp.Status >= 0 && resp.Error == "" {
			targetClient.MarkSuccess()
		} else {
			targetClient.MarkFailure()
		}

		if resp.Error != "" {
			c.JSON(http.StatusOK, gin.H{
				"status":  resp.Status,
				"message": resp.Error,
			})
			return
		}

		// 解析响应数据
		var responseData interface{}
		if err := unmarshalJSON(resp.Data, &responseData); err != nil {
			responseData = string(resp.Data)
		}

		// 返回 cookie 数据
		c.JSON(http.StatusOK, gin.H{
			"status":   resp.Status,
			"message":  "success",
			"group":    req.Group,
			"clientId": targetClient.ClientID,
			"data":     responseData,
		})
	}
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
	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			req.Group = c.Query("group")
			req.ClientID = c.Query("clientId")
			req.ConstantInvoke = c.Query("constantInvoke")
		}
	} else {
		req.Group = c.Query("group")
		req.ClientID = c.Query("clientId")
		req.ConstantInvoke = c.Query("constantInvoke")
	}

	logger.Infof("GetHtml request: group=%s, clientId=%s", req.Group, req.ClientID)

	// 参数验证
	if req.Group == "" {
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "group parameter required",
		})
		return
	}

	// 分配客户端
	var targetClient *client.SekiroClient
	targetClient, err := h.selectTargetClient(req.Group, req.ClientID, req.ConstantInvoke, "_execjs", "document.documentElement.outerHTML")
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

	// 构建 Sekiro 请求数据 - 执行 document.documentElement.outerHTML
	reqData := map[string]interface{}{
		"action": "_execjs",
		"params": "document.documentElement.outerHTML",
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
	sequence := fmt.Sprintf("%s-_html-%d", req.Group, time.Now().UnixNano())

	// 创建 invoke 记录
	timeout := 30 * time.Second // 默认 30 秒超时
	invokeRecord := h.timeoutManager.Add(sequence, req.Group, targetClient.ClientID, reqDataJSON)
	invokeRecord.Timeout = timeout

	// 获取 WebSocket 连接并发送请求
	conn, ok := targetClient.Connection.(*websocket.Conn)
	if !ok {
		h.timeoutManager.Remove(sequence)
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Invalid client connection",
		})
		return
	}

	// 发送 invoke 请求
	err = h.wsHandler.SendInvokeRequest(conn, sequence, req.Group, targetClient.ClientID, reqDataJSON)
	if err != nil {
		h.timeoutManager.Remove(sequence)
		targetClient.MarkFailure()
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Failed to send request: " + err.Error(),
		})
		return
	}

	logger.Infof("GetHtml request sent: sequence=%s, group=%s, clientId=%s", sequence, req.Group, targetClient.ClientID)

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
		c.JSON(http.StatusOK, gin.H{
			"status":  -1,
			"message": "Request timeout",
		})
		return
	case resp := <-responseChan:
		if resp.Status >= 0 && resp.Error == "" {
			targetClient.MarkSuccess()
		} else {
			targetClient.MarkFailure()
		}

		if resp.Error != "" {
			c.JSON(http.StatusOK, gin.H{
				"status":  resp.Status,
				"message": resp.Error,
			})
			return
		}

		// 解析响应数据
		var responseData interface{}
		if err := unmarshalJSON(resp.Data, &responseData); err != nil {
			responseData = string(resp.Data)
		}

		// 返回 HTML 数据
		c.JSON(http.StatusOK, gin.H{
			"status":   resp.Status,
			"message":  "success",
			"group":    req.Group,
			"clientId": targetClient.ClientID,
			"data":     responseData,
		})
	}
}

func (h *APIHandler) selectTargetClient(groupName, clientID, constantInvoke, action string, payload interface{}) (*client.SekiroClient, error) {
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
