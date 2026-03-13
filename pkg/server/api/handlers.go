package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/server/client"
	"github.com/sekiro-go/sekiro-go/pkg/server/forwarder"
	ws "github.com/sekiro-go/sekiro-go/pkg/server/websocket"
)

// APIHandler handles HTTP API requests
type APIHandler struct {
	clientManager  clientManagerIface
	wsHandler      *ws.Handler
	timeoutManager *forwarder.TimeoutManager
}

// clientManagerIface is the interface for client manager (internal)
type clientManagerIface interface {
	GetAllGroups() []string
	GetClientsByGroup(group string) []*client.SekiroClient
	AllocateClient(group string) *client.SekiroClient
	GetClient(group, clientID string) *client.SekiroClient
}

// NewAPIHandler creates a new APIHandler
func NewAPIHandler(manager *client.ClientManager, wsHandler *ws.Handler, timeoutMgr *forwarder.TimeoutManager) *APIHandler {
	return &APIHandler{
		clientManager:  manager,
		wsHandler:      wsHandler,
		timeoutManager: timeoutMgr,
	}
}

// HandleGroupList handles /business/groupList request
func (h *APIHandler) HandleGroupList(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	groups := h.clientManager.GetAllGroups()
	response := map[string]interface{}{
		"status":  0,
		"message": "success",
		"data":    groups,
	}

	h.sendJSONResponse(w, response)
}

// HandleClientQueue handles /business/clientQueue request
func (h *APIHandler) HandleClientQueue(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	group := r.URL.Query().Get("group")
	if group == "" {
		h.sendJSONResponse(w, map[string]interface{}{
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

	response := map[string]interface{}{
		"status":  0,
		"message": "success",
		"data":    clientIDs,
	}

	h.sendJSONResponse(w, response)
}

// HandleInvoke handles /business/invoke request
func (h *APIHandler) HandleInvoke(w http.ResponseWriter, r *http.Request) {
	// 支持 GET 和 POST 方法
	if r.Method != http.MethodPost && r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// 解析请求体
	var req struct {
		Group          string      `json:"group"`
		ClientID       string      `json:"clientId,omitempty"`
		ConstantInvoke string      `json:"constantInvoke,omitempty"`
		Timeout        int         `json:"timeout,omitempty"`
		Action         string      `json:"action"`
		Params         interface{} `json:"params"`
	}

	if r.Method == http.MethodPost {
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			h.sendJSONResponse(w, map[string]interface{}{
				"status":  -1,
				"message": "Invalid JSON: " + err.Error(),
			})
			return
		}
	}

	// GET 方法从查询参数获取
	if r.Method == http.MethodGet {
		req.Group = r.URL.Query().Get("group")
		req.ClientID = r.URL.Query().Get("clientId")
		req.ConstantInvoke = r.URL.Query().Get("constantInvoke")
		req.Action = r.URL.Query().Get("action")
	}

	logger.Infof("Invoke request: group=%s, clientId=%s, action=%s", req.Group, req.ClientID, req.Action)

	// 参数验证
	if req.Group == "" {
		h.sendJSONResponse(w, map[string]interface{}{
			"status":  -1,
			"message": "group parameter required",
		})
		return
	}

	if req.Action == "" {
		h.sendJSONResponse(w, map[string]interface{}{
			"status":  -1,
			"message": "action parameter required",
		})
		return
	}

	// 分配客户端
	var targetClient *client.SekiroClient
	if req.ClientID != "" {
		targetClient = h.clientManager.GetClient(req.Group, req.ClientID)
	} else {
		targetClient = h.clientManager.AllocateClient(req.Group)
	}

	if targetClient == nil {
		h.sendJSONResponse(w, map[string]interface{}{
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

	reqDataJSON, err := json.Marshal(reqData)
	if err != nil {
		h.sendJSONResponse(w, map[string]interface{}{
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
		h.sendJSONResponse(w, map[string]interface{}{
			"status":  -1,
			"message": "Invalid client connection",
		})
		return
	}

	// 发送 invoke 请求
	err = h.wsHandler.SendInvokeRequest(conn, sequence, req.Group, targetClient.ClientID, reqDataJSON)
	if err != nil {
		h.timeoutManager.Remove(sequence)
		// Mark client failure on send error
		targetClient.MarkFailure()
		h.sendJSONResponse(w, map[string]interface{}{
			"status":  -1,
			"message": "Failed to send request: " + err.Error(),
		})
		return
	}

	logger.Infof("Invoke request sent: sequence=%s, group=%s, clientId=%s", sequence, req.Group, targetClient.ClientID)

	// 等待响应
	ctx, cancel := context.WithTimeout(r.Context(), timeout)
	defer cancel()

	responseChan := make(chan *forwarder.InvokeResponse, 1)
	go func() {
		resp, err := h.timeoutManager.Wait(sequence)
		if err != nil {
			responseChan <- &forwarder.InvokeResponse{
				Error: err.Error(),
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
		h.sendJSONResponse(w, map[string]interface{}{
			"status":  -1,
			"message": "Request timeout",
		})
		return
	case resp := <-responseChan:
		// Mark client health based on response
		if resp.Status >= 0 && resp.Error == "" {
			targetClient.MarkSuccess()
		} else {
			targetClient.MarkFailure()
		}

		if resp.Error != "" {
			h.sendJSONResponse(w, map[string]interface{}{
				"status":  resp.Status,
				"message": resp.Error,
			})
			return
		}

		// 解析响应数据
		var responseData interface{}
		if err := json.Unmarshal(resp.Data, &responseData); err != nil {
			// 如果响应不是有效 JSON，当作字符串处理
			responseData = string(resp.Data)
		}

		// 如果 status 为 -1 但没有 Error，说明是异常情况
		message := "success"
		if resp.Status < 0 {
			message = "unknown error"
		}

		h.sendJSONResponse(w, map[string]interface{}{
			"status":  resp.Status,
			"message": message,
			"data":    responseData,
		})
	}
}

func (h *APIHandler) sendJSONResponse(w http.ResponseWriter, data map[string]interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(data); err != nil {
		logger.Errorf("Failed to encode JSON response: %v", err)
	}
}
