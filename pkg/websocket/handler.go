package websocket

import (
	"context"
	"errors"
	"net"
	"sync"
	"time"

	json "github.com/goccy/go-json"

	"github.com/gorilla/websocket"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/transport"
)

// ensureDefaultActions ensures default actions exist for a group
func (h *Handler) ensureDefaultActions(groupName string) {
	db := database.GetDB()
	if db == nil {
		return
	}
	for _, actionName := range model.DefaultGroupActions {
		var count int64
		if err := db.Model(&model.GroupAction{}).
			Where("group_name = ? AND action_name = ?", groupName, actionName).
			Count(&count).Error; err != nil {
			logger.Warnf("Failed to check action existence: group=%s, action=%s, err=%v", groupName, actionName, err)
			continue
		}

		if count != 0 {
			continue
		}

		action := model.GroupAction{
			GroupName:  groupName,
			ActionName: actionName,
			CreateDate: time.Now(),
		}
		if err := db.Create(&action).Error; err != nil {
			logger.Warnf("Failed to create default action: group=%s, action=%s, err=%v", groupName, actionName, err)
			continue
		}
		logger.Infof("Default action created: group=%s, action=%s", groupName, actionName)
	}
}

// isGroupRegistered checks if a group exists in group_config table
func (h *Handler) isGroupRegistered(groupName string) bool {
	db := database.GetDB()
	if db == nil {
		return false
	}
	var count int64
	if err := db.Model(&model.GroupConfig{}).
		Where("group_name = ?", groupName).
		Count(&count).Error; err != nil {
		logger.Warnf("Failed to check group registration: group=%s, err=%v", groupName, err)
		return false
	}
	return count > 0
}

// MessageType defines Rpc message types
type MessageType string

const (
	MessageTypeHeartbeat      MessageType = "heartbeat"
	MessageTypeInvoke         MessageType = "invoke"
	MessageTypeInvokeResponse MessageType = "invoke_response"
	MessageTypeInvokeStream   MessageType = "invoke_stream"
	MessageTypeBind           MessageType = "bind"
)

// RpcMessage represents a Rpc protocol message
type RpcMessage struct {
	Type      MessageType     `json:"type"`
	Sequence  string          `json:"sequence,omitempty"`
	RpcSeq    string          `json:"__sekiro_seq__,omitempty"`
	Group     string          `json:"group,omitempty"`
	ClientID  string          `json:"clientId,omitempty"`
	Data      json.RawMessage `json:"data,omitempty"`
	Error     string          `json:"error,omitempty"`
	Status    int             `json:"status,omitempty"`
	Done      bool            `json:"done,omitempty"`
	Timestamp int64           `json:"timestamp,omitempty"`
}

// GetSequence 获取消息序列号，兼容两种字段格式
func (m *RpcMessage) GetSequence() string {
	if m.RpcSeq != "" {
		return m.RpcSeq
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

// Handler handles WebSocket connections for Rpc clients
type Handler struct {
	clientManager    *client.ClientManager
	timeoutManager   *forwarder.TimeoutManager
	heartbeatTimeout time.Duration
	eventBus         *eventbus.EventBus
	mu               sync.RWMutex
}

// HandlerConfig holds configuration for Handler
type HandlerConfig struct {
	HeartbeatTimeout time.Duration
}

// DefaultHandlerConfig returns default handler configuration
func DefaultHandlerConfig() *HandlerConfig {
	return &HandlerConfig{
		HeartbeatTimeout: 60 * time.Second,
	}
}

// NewHandler creates a new Handler
func NewHandler(manager *client.ClientManager, timeoutMgr *forwarder.TimeoutManager, config *HandlerConfig, eventBus *eventbus.EventBus) *Handler {
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
		eventBus:         eventBus,
	}
}

// HandleConnection handles a WebSocket connection
func (h *Handler) HandleConnection(ctx context.Context, conn *websocket.Conn, group, clientID string) {
	logger.Infof("WebSocket connection established: group=%s, clientId=%s", group, clientID)

	defer func() {
		if r := recover(); r != nil {
			logger.Warnf("WebSocket handler recovered from panic: group=%s, clientId=%s, error=%v", group, clientID, r)
		}
	}()

	// Wrap the WebSocket connection in a transport.Connection for the RpcClient.
	// Keep the raw *websocket.Conn for read-side operations (ReadMessage, SetReadDeadline).
	wsTransport := transport.NewWSConnection(conn)
	sekiroClient := client.NewRpcClient(group, clientID, wsTransport)
	sekiroClient.SetStatus(client.StatusOnline)

	// 设置健康降级回调，通过 EventBus 发布事件
	if h.eventBus != nil {
		sekiroClient.OnHealthDegraded = func(c *client.RpcClient) {
			h.eventBus.Publish(eventbus.EventClientHealthDegraded, &eventbus.ClientHealthDegradedEvent{
				Group:     c.Group,
				ClientID:  c.ClientID,
				FailCount: c.GetFailCount(),
				Timestamp: time.Now(),
			})
		}
	}

	isRegistered := h.isGroupRegistered(group)
	if isRegistered {
		logger.Infof("Connected to registered group: group=%s", group)
		h.ensureDefaultActions(group)
	} else {
		logger.Infof("Connected to anonymous group (not registered): group=%s", group)
	}

	remoteIP := extractRemoteIP(conn)
	now := time.Now()

	if db := database.GetDB(); db != nil {
		device := model.GroupDevice{
			GroupName:      group,
			DeviceID:       clientID,
			RemoteIP:       remoteIP,
			LastActiveTime: now,
		}

		if err := db.Where("group_name = ? AND device_id = ?", group, clientID).
			FirstOrCreate(&device).Error; err != nil {
			logger.Warnf("Failed to create device record: %v", err)
		} else {
			logger.Infof("Device record created/updated: group=%s, deviceId=%s, remoteIP=%s", group, clientID, remoteIP)
		}
	}

	h.clientManager.Register(sekiroClient)

	var closed bool

	defer func() {
		closed = true
		sekiroClient.SetStatus(client.StatusOffline)
		h.clientManager.Unregister(group, clientID)
		wsTransport.Close()
		logger.Infof("WebSocket connection closed: group=%s, clientId=%s", group, clientID)
	}()

	for {
		if closed {
			return
		}

		select {
		case <-ctx.Done():
			logger.Infof("WebSocket handler context cancelled: group=%s, clientId=%s", group, clientID)
			return
		default:
		}

		if time.Since(sekiroClient.LastActive) > h.heartbeatTimeout {
			logger.Warnf("Heartbeat timeout: group=%s, clientId=%s", group, clientID)
			return
		}

		conn.SetReadDeadline(time.Now().Add(h.heartbeatTimeout / 2))

		_, message, err := conn.ReadMessage()
		if err != nil {
			if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				continue
			}
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure, websocket.CloseNormalClosure) {
				logger.Debugf("WebSocket read error: %v", err)
			} else {
				logger.Debugf("WebSocket normal close: %v", err)
			}
			return
		}

		sekiroClient.UpdateActive()
		h.processMessage(ctx, sekiroClient, message)
	}
}

// processMessage processes a WebSocket message
func (h *Handler) processMessage(ctx context.Context, sekiroClient *client.RpcClient, data []byte) {
	// logger.Debugf("Received raw message")

	var msg RpcMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		logger.Errorf("Failed to parse message: %v", err)
		h.sendError(sekiroClient, "invalid message format", "")
		return
	}

	sequence := msg.GetSequence()
	// logger.Debugf("Parsed message: type=%s, sequence=%s, status=%d, Error=%s", msg.Type, sequence, msg.Status, msg.Error)

	if msg.Type == MessageTypeInvokeResponse || (sequence != "" && msg.Type == "") {
		h.handleInvokeResponse(&msg, data)
		return
	}

	switch msg.Type {
	case MessageTypeHeartbeat:
		h.handleHeartbeat(sekiroClient, &msg)
	case MessageTypeInvokeStream:
		h.handleInvokeStream(&msg)
	default:
		// 客户端"echo 类"畸形响应（type 为空、seq 为空，常见于 client 把服务端心跳响应当作请求处理后回的失败包）
		// 不能再通过 sendError 回包，否则会与客户端形成"unknown message type ↔ 缺少 action"的无限回环。
		// 仅记日志静默丢弃。
		if msg.Type == "" && sequence == "" {
			logger.Warnf("Discarding malformed message (empty type and sequence): %s", string(data))
			return
		}
		logger.Warnf("Unknown message type: %s", msg.Type)
		h.sendError(sekiroClient, "unknown message type", sequence)
	}
}

// handleInvokeStream handles a streaming invoke response chunk.
func (h *Handler) handleInvokeStream(msg *RpcMessage) {
	sequence := msg.GetSequence()
	if sequence == "" {
		logger.Warnf("Invoke stream chunk missing sequence number")
		return
	}

	chunk := &forwarder.StreamChunk{
		Data:   msg.Data,
		Error:  msg.Error,
		Status: msg.Status,
		Done:   msg.Done,
	}
	if !h.timeoutManager.PushStreamChunk(sequence, chunk) {
		logger.Debugf("Invoke stream chunk for missing request: sequence=%s", sequence)
		return
	}
	if msg.Done || msg.Error != "" {
		if !h.timeoutManager.CompleteStream(sequence) {
			logger.Debugf("Invoke stream completion for missing request: sequence=%s", sequence)
		}
	}
}

// handleHeartbeat handles heartbeat messages
func (h *Handler) handleHeartbeat(sekiroClient *client.RpcClient, msg *RpcMessage) {
	// logger.Debugf("Heartbeat received from %s/%s", msg.Group, msg.ClientID)

	if msg.Group != "" && msg.ClientID != "" {
		if sc := h.clientManager.GetClient(msg.Group, msg.ClientID); sc != nil {
			sc.MarkSuccess()
		}

		if db := database.GetDB(); db != nil {
			if err := db.Model(&model.GroupDevice{}).
				Where("group_name = ? AND device_id = ?", msg.Group, msg.ClientID).
				Update("last_active_time", time.Now()).Error; err != nil {
				logger.Warnf("Failed to update device last_active_time: %v", err)
			}
		}
	}

	response := RpcMessage{
		Type:      MessageTypeHeartbeat,
		Timestamp: time.Now().UnixMilli(),
	}
	h.sendMessage(sekiroClient, &response)
}

// handleInvokeResponse handles invoke response messages
func (h *Handler) handleInvokeResponse(msg *RpcMessage, rawData []byte) {
	sequence := msg.GetSequence()
	if sequence == "" {
		logger.Warnf("Invoke response missing sequence number")
		return
	}

	var responseData []byte
	var errorMessage string

	if msg.Error != "" {
		errorMessage = msg.Error
	} else if msg.Status < 0 {
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
		responseData = msg.Data
	} else if msg.Status >= 0 {
		var rawMsg map[string]interface{}
		if err := json.Unmarshal(rawData, &rawMsg); err == nil {
			delete(rawMsg, "__sekiro_seq__")
			delete(rawMsg, "status")
			delete(rawMsg, "code")
			delete(rawMsg, "message")
			delete(rawMsg, "type")
			delete(rawMsg, "error")

			if len(rawMsg) > 0 {
				responseData, _ = json.Marshal(rawMsg)
			} else {
				responseData = []byte("{}")
			}
		} else {
			responseData = []byte("{}")
		}
		logger.Infof("Invoke response with empty data but status>=0, handler may have returned object: sequence=%s", sequence)
	}

	logger.Infof("Invoke response received: sequence=%s, status=%d, Error=%s", sequence, msg.Status, errorMessage)

	response := &forwarder.InvokeResponse{
		Data:   responseData,
		Error:  errorMessage,
		Status: msg.Status,
	}

	if sc := h.clientManager.GetClient(msg.Group, msg.ClientID); sc != nil {
		if msg.Status >= 0 {
			sc.MarkSuccess()
		} else {
			sc.MarkFailure()
		}
	}

	if !h.timeoutManager.Complete(sequence, response) {
		logger.Debugf("Invoke response for expired request: sequence=%s", sequence)
	}
}

// sendMessage sends a message to the client via its transport connection.
func (h *Handler) sendMessage(sekiroClient *client.RpcClient, msg *RpcMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		logger.Errorf("Failed to marshal message: %v", err)
		return
	}

	if sekiroClient == nil || sekiroClient.Connection == nil {
		logger.Warnf("sendMessage called with nil client or connection")
		return
	}

	if err := sekiroClient.Connection.Send(data); err != nil {
		logger.Debugf("Failed to send message: %v", err)
	}
}

// sendError sends an error message to the client
func (h *Handler) sendError(sekiroClient *client.RpcClient, errorMsg, sequence string) {
	msg := RpcMessage{
		Type:      "error",
		Error:     errorMsg,
		Sequence:  sequence,
		Timestamp: time.Now().UnixMilli(),
	}
	h.sendMessage(sekiroClient, &msg)
}

// SendInvokeRequest sends an invoke request to a client.
// The transport connection is obtained from the RpcClient.
func (h *Handler) SendInvokeRequest(sekiroClient *client.RpcClient, sequence, group, clientID string, data []byte) error {
	var reqData map[string]interface{}
	if err := json.Unmarshal(data, &reqData); err != nil {
		logger.Errorf("Failed to parse request data: %v", err)
		return err
	}

	msgData := make(map[string]interface{})
	for k, v := range reqData {
		msgData[k] = v
	}
	msgData["__sekiro_seq__"] = sequence

	fullMsg := make(map[string]interface{})
	fullMsg["type"] = MessageTypeInvoke
	fullMsg["group"] = group
	fullMsg["clientId"] = clientID
	fullMsg["timestamp"] = time.Now().UnixMilli()
	for k, v := range msgData {
		fullMsg[k] = v
	}

	msgDataJSON, err := json.Marshal(fullMsg)
	if err != nil {
		logger.Errorf("Failed to marshal message: %v", err)
		return err
	}

	logger.Infof("Sending invoke message")

	if sekiroClient == nil || sekiroClient.Connection == nil {
		return errors.New("invalid client connection")
	}

	return sekiroClient.Connection.Send(msgDataJSON)
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
