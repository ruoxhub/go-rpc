package websocket

import (
	"context"
	"encoding/json"
	"net"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/database"
	"github.com/sekiro-go/sekiro-go/pkg/model"
	"github.com/sekiro-go/sekiro-go/pkg/server/client"
	"github.com/sekiro-go/sekiro-go/pkg/server/forwarder"
)

// DefaultGroupActions 默认分组 Actions 列表
// 当设备连接到正式分组时，这些 Actions 会被自动添加到 group_actions 表中
var DefaultGroupActions = []string{"invoke", "execJs", "getHtml", "getCookie"}

// ensureDefaultActions ensures default actions exist for a group
// 当设备连接到正式分组时，自动添加默认 Actions
func (h *Handler) ensureDefaultActions(groupName string) {
	for _, actionName := range DefaultGroupActions {
		// 检查 action 是否已存在
		var count int64
		if err := database.GetDB().Model(&model.GroupAction{}).
			Where("group_name = ? AND action_name = ?", groupName, actionName).
			Count(&count).Error; err != nil {
			logger.Warnf("Failed to check action existence: group=%s, action=%s, err=%v", groupName, actionName, err)
			continue
		}

		if count == 0 {
			// 添加默认 action
			action := model.GroupAction{
				GroupName:  groupName,
				ActionName: actionName,
				CreateDate: time.Now(),
			}
			if err := database.GetDB().Create(&action).Error; err != nil {
				logger.Warnf("Failed to create default action: group=%s, action=%s, err=%v", groupName, actionName, err)
			} else {
				logger.Infof("Default action created: group=%s, action=%s", groupName, actionName)
			}
		}
	}
}

// isGroupRegistered checks if a group exists in group_config table
// 检查分组是否已注册（存在于 group_config 表中）
func (h *Handler) isGroupRegistered(groupName string) bool {
	var count int64
	if err := database.GetDB().Model(&model.GroupConfig{}).
		Where("group_name = ?", groupName).
		Count(&count).Error; err != nil {
		logger.Warnf("Failed to check group registration: group=%s, err=%v", groupName, err)
		return false
	}
	return count > 0
}

// MessageType defines Sekiro message types
type MessageType string

const (
	// MessageTypeHeartbeat is the heartbeat message type
	MessageTypeHeartbeat MessageType = "heartbeat"
	// MessageTypeInvoke is the invoke request message type
	MessageTypeInvoke MessageType = "invoke"
	// MessageTypeInvokeResponse is the invoke response message type
	MessageTypeInvokeResponse MessageType = "invoke_response"
	// MessageTypeBind is the bind message type (deprecated)
	MessageTypeBind MessageType = "bind"
)

// SekiroMessage represents a Sekiro protocol message
type SekiroMessage struct {
	Type      MessageType     `json:"type"`
	Sequence  string          `json:"sequence,omitempty"` // Sekiro 协议字段
	SekiroSeq string          `json:"__sekiro_seq__,omitempty"` // JavaScript 客户端使用的字段
	Group     string          `json:"group,omitempty"`
	ClientID  string          `json:"clientId,omitempty"`
	Data      json.RawMessage `json:"data,omitempty"`
	Error     string          `json:"error,omitempty"`
	Status    int             `json:"status,omitempty"`
	Timestamp int64           `json:"timestamp,omitempty"`
}

// GetSequence 获取消息序列号，兼容两种字段格式
func (m *SekiroMessage) GetSequence() string {
	if m.SekiroSeq != "" {
		return m.SekiroSeq
	}
	return m.Sequence
}

// extractRemoteIP extracts the remote IP address from WebSocket connection
func extractRemoteIP(conn *websocket.Conn) string {
	if conn == nil || conn.UnderlyingConn() == nil {
		return ""
	}
	remoteAddr := conn.UnderlyingConn().RemoteAddr()
	if remoteAddr == nil {
		return ""
	}
	ip, _, _ := net.SplitHostPort(remoteAddr.String())
	return ip
}

// Handler handles WebSocket connections for Sekiro clients
type Handler struct {
	clientManager  *client.ClientManager
	timeoutManager *forwarder.TimeoutManager
	// heartbeatTimeout is the timeout for heartbeat messages
	heartbeatTimeout time.Duration
	// mu protects handlers
	mu sync.RWMutex
}

// HandlerConfig holds configuration for Handler
type HandlerConfig struct {
	// HeartbeatTimeout is the timeout for heartbeat messages
	HeartbeatTimeout time.Duration
}

// DefaultHandlerConfig returns default handler configuration
func DefaultHandlerConfig() *HandlerConfig {
	return &HandlerConfig{
		HeartbeatTimeout: 60 * time.Second,
	}
}

// NewHandler creates a new Handler
func NewHandler(manager *client.ClientManager, timeoutMgr *forwarder.TimeoutManager, config *HandlerConfig) *Handler {
	if config == nil {
		config = DefaultHandlerConfig()
	}
	if timeoutMgr == nil {
		timeoutMgr = forwarder.NewTimeoutManager(nil)
	}

	return &Handler{
		clientManager:    manager,
		timeoutManager:   timeoutMgr,
		heartbeatTimeout: config.HeartbeatTimeout,
	}
}

// HandleConnection handles a WebSocket connection
func (h *Handler) HandleConnection(ctx context.Context, conn *websocket.Conn, group, clientID string) {
	logger.Infof("WebSocket connection established: group=%s, clientId=%s", group, clientID)

	// Create Sekiro client
	sekiroClient := client.NewSekiroClient(group, clientID, conn)
	sekiroClient.SetStatus(client.StatusOnline)

	// 检查分组是否已注册（存在于 group_config 表中）
	isRegistered := h.isGroupRegistered(group)
	if isRegistered {
		logger.Infof("Connected to registered group: group=%s", group)
		// 正式分组：自动添加默认 Actions
		h.ensureDefaultActions(group)
	} else {
		logger.Infof("Connected to anonymous group (not registered): group=%s", group)
		// 匿名分组：设备归入匿名分组管理
	}

	// Create or update device record in database
	remoteIP := extractRemoteIP(conn)
	now := time.Now()
	device := model.GroupDevice{
		GroupName:      group,
		DeviceID:       clientID,
		RemoteIP:       remoteIP,
		LastActiveTime: now,
	}

	// Use FirstOrCreate to avoid duplicate inserts
	// If record exists, update LastActiveTime
	if err := database.GetDB().Where("group_name = ? AND device_id = ?", group, clientID).
		FirstOrCreate(&device).Error; err != nil {
		logger.Warnf("Failed to create device record: %v", err)
		// Database error doesn't affect connection establishment
	} else {
		logger.Infof("Device record created/updated: group=%s, deviceId=%s, remoteIP=%s", group, clientID, remoteIP)
	}

	// Register client
	h.clientManager.Register(sekiroClient)

	// Ensure cleanup on exit
	defer func() {
		sekiroClient.SetStatus(client.StatusOffline)
		h.clientManager.Unregister(group, clientID)
		conn.Close()
		logger.Infof("WebSocket connection closed: group=%s, clientId=%s", group, clientID)
	}()

	// Start heartbeat checker
	heartbeatTicker := time.NewTicker(h.heartbeatTimeout / 2)
	defer heartbeatTicker.Stop()

	// Message processing loop
	for {
		select {
		case <-ctx.Done():
			return
		case <-heartbeatTicker.C:
			// Check if client is still alive
			if time.Since(sekiroClient.LastActive) > h.heartbeatTimeout {
				logger.Warnf("Heartbeat timeout: group=%s, clientId=%s", group, clientID)
				return
			}
		default:
			// Set read deadline
			conn.SetReadDeadline(time.Now().Add(h.heartbeatTimeout))

			// Read message
			_, message, err := conn.ReadMessage()
			if err != nil {
				// 区分正常关闭和异常断开
				if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure, websocket.CloseNormalClosure) {
					logger.Debugf("WebSocket read error: %v", err)
				} else {
					// 正常关闭（如 CloseNormalClosure, CloseGoingAway）不记录为错误
					logger.Debugf("WebSocket normal close: %v", err)
				}
				return
			}

			// Update last active time
			sekiroClient.UpdateActive()

			// Process message
			h.processMessage(ctx, conn, message)
		}
	}
}

// processMessage processes a WebSocket message
func (h *Handler) processMessage(ctx context.Context, conn *websocket.Conn, data []byte) {
	logger.Infof("Received raw message: %s", string(data))

	var msg SekiroMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		logger.Errorf("Failed to parse message: %v", err)
		h.sendError(conn, "invalid message format", "")
		return
	}

	sequence := msg.GetSequence()
	logger.Infof("Parsed message: type=%s, sequence=%s, status=%d, Data=%s, Error=%s", msg.Type, sequence, msg.Status, string(msg.Data), msg.Error)

	// 如果消息类型为invoke_response，或者消息包含__sekiro_seq__和 status 字段但没有 type 字段
	// 则视为 invoke_response（兼容 JavaScript 客户端的响应格式）
	if msg.Type == MessageTypeInvokeResponse || (sequence != "" && msg.Type == "") {
		h.handleInvokeResponse(conn, &msg, data)
		return
	}

	switch msg.Type {
	case MessageTypeHeartbeat:
		h.handleHeartbeat(conn, &msg)
	default:
		logger.Warnf("Unknown message type: %s", msg.Type)
		h.sendError(conn, "unknown message type", sequence)
	}
}

// handleHeartbeat handles heartbeat messages
func (h *Handler) handleHeartbeat(conn *websocket.Conn, msg *SekiroMessage) {
	logger.Debugf("Heartbeat received from %s/%s", msg.Group, msg.ClientID)

	// Mark client as healthy on successful heartbeat
	if msg.Group != "" && msg.ClientID != "" {
		sekiroClient := h.clientManager.GetClient(msg.Group, msg.ClientID)
		if sekiroClient != nil {
			sekiroClient.MarkSuccess()
		}

		// Update LastActiveTime in database
		if err := database.GetDB().Model(&model.GroupDevice{}).
			Where("group_name = ? AND device_id = ?", msg.Group, msg.ClientID).
			Update("last_active_time", time.Now()).Error; err != nil {
			logger.Warnf("Failed to update device last_active_time: %v", err)
		}
	}

	// Send heartbeat response
	response := SekiroMessage{
		Type:      MessageTypeHeartbeat,
		Timestamp: time.Now().UnixMilli(),
	}
	h.sendMessage(conn, &response)
}

// handleInvokeResponse handles invoke response messages
func (h *Handler) handleInvokeResponse(conn *websocket.Conn, msg *SekiroMessage, rawData []byte) {
	sequence := msg.GetSequence()
	if sequence == "" {
		logger.Warnf("Invoke response missing sequence number")
		return
	}

	// JavaScript 客户端返回的响应格式：
	// 成功时：{"data": "...", "code": 0, "status": 0, "__sekiro_seq__": "..."}
	// 或者：{"result": "...", "code": 0, "status": 0, "__sekiro_seq__": "..."} (当 handler 返回对象时)
	// 失败时：{"message": "...", "status": -1, "__sekiro_seq__": "..."}
	//
	// msg.Data 是从 JSON 中解析的 data 字段的原始内容（json.RawMessage）
	// 如果 Data 为空但 status >= 0，说明 handler 返回的是对象而不是字符串，需要特殊处理

	var responseData []byte
	var errorMessage string

	// 提取错误信息：优先使用 error 字段，如果不存在则使用 message 字段（兼容 JavaScript 客户端）
	if msg.Error != "" {
		errorMessage = msg.Error
	} else if msg.Status < 0 {
		// 重新解析原始消息，尝试提取 message 字段作为错误信息
		var rawMsg map[string]interface{}
		if err := json.Unmarshal(rawData, &rawMsg); err == nil {
			if msgVal, ok := rawMsg["message"]; ok {
				if msgStr, ok := msgVal.(string); ok {
					errorMessage = msgStr
				}
			}
		}
	}

	if len(msg.Data) > 0 {
		// 有 data 字段，直接使用
		responseData = msg.Data
	} else if msg.Status >= 0 {
		// 成功响应但 data 为空，可能是 handler 返回了对象
		// 重新解析原始消息，提取除元数据字段外的所有内容作为数据
		var rawMsg map[string]interface{}
		if err := json.Unmarshal(rawData, &rawMsg); err == nil {
			// 移除元数据字段
			delete(rawMsg, "__sekiro_seq__")
			delete(rawMsg, "status")
			delete(rawMsg, "code")
			delete(rawMsg, "message")
			delete(rawMsg, "type")
			delete(rawMsg, "error")

			// 如果还有剩余内容，作为数据返回
			if len(rawMsg) > 0 {
				responseData, _ = json.Marshal(rawMsg)
				logger.Infof("Invoke response: extracted data from object response: %s", string(responseData))
			} else {
				responseData = []byte("{}")
			}
		} else {
			responseData = []byte("{}")
		}
		logger.Infof("Invoke response with empty data but status>=0, handler may have returned object: sequence=%s", sequence)
	}

	logger.Infof("Invoke response received: sequence=%s, status=%d, Data=%s, Error=%s", sequence, msg.Status, string(responseData), errorMessage)

	// Complete the invoke request
	response := &forwarder.InvokeResponse{
		Data:   responseData,
		Error:  errorMessage,
		Status: msg.Status,
	}

	// Mark client health based on response status
	if msg.Status >= 0 {
		// Success - mark client as healthy
		sekiroClient := h.clientManager.GetClient(msg.Group, msg.ClientID)
		if sekiroClient != nil {
			sekiroClient.MarkSuccess()
		}
	} else {
		// Failure - mark client failure
		sekiroClient := h.clientManager.GetClient(msg.Group, msg.ClientID)
		if sekiroClient != nil {
			sekiroClient.MarkFailure()
		}
	}

	if !h.timeoutManager.Complete(sequence, response) {
		logger.Debugf("Invoke response for expired request: sequence=%s", sequence)
	}
}

// sendMessage sends a message to the client
func (h *Handler) sendMessage(conn *websocket.Conn, msg *SekiroMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		logger.Errorf("Failed to marshal message: %v", err)
		return
	}

	conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
		logger.Debugf("Failed to send message: %v", err)
	}
}

// sendError sends an error message to the client
func (h *Handler) sendError(conn *websocket.Conn, errorMsg, sequence string) {
	msg := SekiroMessage{
		Type:      "error",
		Error:     errorMsg,
		Sequence:  sequence,
		Timestamp: time.Now().UnixMilli(),
	}
	h.sendMessage(conn, &msg)
}

// SendInvokeRequest sends an invoke request to a client
// The message format is compatible with the JavaScript client
func (h *Handler) SendInvokeRequest(conn *websocket.Conn, sequence, group, clientID string, data []byte) error {
	// Parse the request data
	var reqData map[string]interface{}
	if err := json.Unmarshal(data, &reqData); err != nil {
		logger.Errorf("Failed to parse request data: %v", err)
		return err
	}

	// Build message compatible with JavaScript client
	// The JavaScript client expects: { "action": "...", "__sekiro_seq__": "...", ... }
	msgData := make(map[string]interface{})
	for k, v := range reqData {
		msgData[k] = v
	}
	msgData["__sekiro_seq__"] = sequence

	// Marshal the message with action and sequence at root level
	fullMsg := make(map[string]interface{})
	fullMsg["type"] = MessageTypeInvoke
	fullMsg["group"] = group
	fullMsg["clientId"] = clientID
	fullMsg["timestamp"] = time.Now().UnixMilli()
	// Merge request data at root level
	for k, v := range msgData {
		fullMsg[k] = v
	}

	msgDataJSON, err := json.Marshal(fullMsg)
	if err != nil {
		logger.Errorf("Failed to marshal message: %v", err)
		return err
	}

	logger.Infof("Sending invoke message: %s", string(msgDataJSON))

	conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	if err := conn.WriteMessage(websocket.TextMessage, msgDataJSON); err != nil {
		logger.Debugf("Failed to send message: %v", err)
		return err
	}

	return nil
}

// GetTimeoutManager returns the timeout manager
func (h *Handler) GetTimeoutManager() *forwarder.TimeoutManager {
	return h.timeoutManager
}

// Shutdown shuts down the handler
func (h *Handler) Shutdown() {
	if h.timeoutManager != nil {
		h.timeoutManager.Shutdown()
	}
}
