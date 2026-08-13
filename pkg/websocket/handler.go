package websocket

import (
	"context"
	"errors"
	"fmt"
	"net"
	"strings"
	"sync"
	"time"

	json "github.com/goccy/go-json"

	"github.com/gorilla/websocket"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/protocol"
	"github.com/mrh30000/go-rpc/pkg/transport"
)

// ensureDefaultActions ensures default actions exist for a group
func (h *Handler) ensureDefaultActions(groupName string) {
	if h.groupRepo == nil {
		return
	}
	if err := h.groupRepo.EnsureDefaultActions(groupName); err != nil {
		logger.Warnf("Failed to ensure default actions: group=%s, err=%v", groupName, err)
	}
}

// isGroupRegistered checks if a group exists in group_config table
func (h *Handler) isGroupRegistered(groupName string) bool {
	if h.groupRepo == nil {
		return false
	}
	registered, err := h.groupRepo.IsGroupRegistered(groupName)
	if err != nil {
		logger.Warnf("Failed to check group registration: group=%s, err=%v", groupName, err)
		return false
	}
	return registered
}

type MessageType = protocol.WSMessageType
type RpcMessage = protocol.WSMessage

const (
	MessageTypeRegistered     = protocol.MessageTypeRegistered
	MessageTypeHeartbeat      = protocol.MessageTypeHeartbeat
	MessageTypeInvoke         = protocol.MessageTypeInvoke
	MessageTypeInvokeResponse = protocol.MessageTypeInvokeResponse
	MessageTypeInvokeStream   = protocol.MessageTypeInvokeStream
	MessageTypeBind           = protocol.MessageTypeBind
)

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
	groupRepo        repository.GroupRepository
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
func NewHandler(manager *client.ClientManager, timeoutMgr *forwarder.TimeoutManager, config *HandlerConfig, eventBus *eventbus.EventBus, groupRepo repository.GroupRepository) *Handler {
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
		groupRepo:        groupRepo,
	}
}

// HandleConnection handles a legacy WebSocket connection.
func (h *Handler) HandleConnection(ctx context.Context, conn *websocket.Conn, group, clientID string) {
	h.HandleConnectionWithRegistration(ctx, conn, group, clientID, protocol.LegacyRegistration())
}

// HandleConnectionWithRegistration handles a WebSocket connection with negotiated metadata.
func (h *Handler) HandleConnectionWithRegistration(ctx context.Context, conn *websocket.Conn, group, clientID string, registration protocol.Registration) {
	defer func() {
		if r := recover(); r != nil {
			logger.Warnf("WebSocket handler recovered from panic: group=%s, clientId=%s, error=%v", group, clientID, r)
		}
	}()

	// Wrap the WebSocket connection in a transport.Connection for the RpcClient.
	// Keep the raw *websocket.Conn for read-side operations (ReadMessage, SetReadDeadline).
	wsTransport := transport.NewWSConnection(conn)
	sekiroClient := client.NewRpcClient(group, clientID, wsTransport)
	sekiroClient.SetProtocol(registration.ProtocolVersion, registration.Capabilities)

	if !registration.Legacy {
		registered := &RpcMessage{
			Type:            MessageTypeRegistered,
			ProtocolVersion: registration.ProtocolVersion,
			Capabilities:    registration.Capabilities,
			Timestamp:       time.Now().UnixMilli(),
		}
		if err := h.sendMessage(sekiroClient, registered); err != nil {
			logger.Warnf("Registration confirmation failed: group=%s, clientId=%s, err=%v", group, clientID, err)
			return
		}
	}

	sekiroClient.SetStatus(client.StatusOnline)

	// 设置熔断器状态变更回调，通过 EventBus 发布事件
	if h.eventBus != nil {
		sekiroClient.SetCircuitBreakerCallback(func(from, to client.CircuitState) {
			eventbus.PublishTyped(h.eventBus, eventbus.EventCircuitBreakerStateChanged, eventbus.CircuitBreakerStateEvent{
				Group:     group,
				ClientID:  clientID,
				From:      from.String(),
				To:        to.String(),
				Timestamp: time.Now(),
			})
			if from == client.CircuitClosed && to == client.CircuitOpen {
				eventbus.PublishTyped(h.eventBus, eventbus.EventClientHealthDegraded, eventbus.ClientHealthDegradedEvent{
					Group:     group,
					ClientID:  clientID,
					FailCount: sekiroClient.GetFailCount(),
					Timestamp: time.Now(),
				})
			}
		})
	}

	isRegistered := h.isGroupRegistered(group)
	sekiroClient.SetRegisteredGroup(isRegistered)
	if isRegistered {
		h.ensureDefaultActions(group)
	} else {
		logger.Debugf("Connected to anonymous group (not registered): group=%s", group)
	}

	if isRegistered {
		remoteIP := extractRemoteIP(conn)
		now := time.Now()
		if h.groupRepo != nil {
			device := model.GroupDevice{
				GroupName:      group,
				DeviceID:       clientID,
				RemoteIP:       remoteIP,
				LastActiveTime: now,
			}

			if err := h.groupRepo.UpsertDevice(&device); err != nil {
				logger.Warnf("Failed to create device record: %v", err)
			}
		}
	}

	h.clientManager.Register(sekiroClient)

	var closed bool

	defer func() {
		closed = true
		sekiroClient.SetStatus(client.StatusOffline)
		h.clientManager.Unregister(group, clientID)
		wsTransport.Close()
	}()

	for {
		if closed {
			return
		}

		select {
		case <-ctx.Done():
			return
		default:
		}

		// 读取 LastActive 走 getter,避免与 UpdateActive 的写操作产生 data race。
		if time.Since(sekiroClient.GetLastActive()) > h.heartbeatTimeout {
			logger.Warnf("Heartbeat timeout: group=%s, clientId=%s", group, clientID)
			return
		}

		// 限制单条消息大小,防止恶意客户端发送超大帧导致 OOM。
		// 与 TCP 协议层 bodyLen 上限 (10MB) 对齐。
		conn.SetReadLimit(10 * 1024 * 1024)
		conn.SetReadDeadline(time.Now().Add(h.heartbeatTimeout / 2))

		_, message, err := conn.ReadMessage()
		if err != nil {
			if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				// Read deadline 超时：主动发 Ping 探测连接活性。
				// TCP 半死状态（对端静默断开、NAT 超时等）下 WriteMessage 可能仍成功（OS 缓冲），
				// 但 WriteControl(Ping) 使用独立帧缓冲且 deadline 短，能更快暴露死连接。
				if pingErr := conn.WriteControl(
					websocket.PingMessage, nil,
					time.Now().Add(5*time.Second),
				); pingErr != nil {
					logger.Warnf("Ping probe failed, connection likely dead: group=%s, clientId=%s, err=%v", group, clientID, pingErr)
					return
				}
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
	case MessageTypeBind:
		h.handleBind(sekiroClient, &msg)
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

// handleBind syncs the actions reported by a client into the registered group action list.
func (h *Handler) handleBind(sekiroClient *client.RpcClient, msg *RpcMessage) {
	groupName := msg.Group
	if groupName == "" {
		groupName = sekiroClient.Group
	}
	if groupName == "" || len(msg.Actions) == 0 {
		return
	}
	if !h.isGroupRegistered(groupName) {
		logger.Debugf("Skipping action sync for anonymous group: group=%s", groupName)
		return
	}

	if h.groupRepo == nil {
		return
	}

	seen := make(map[string]struct{}, len(msg.Actions))
	for _, actionName := range msg.Actions {
		actionName = strings.TrimSpace(actionName)
		if actionName == "" || len(actionName) > 64 {
			continue
		}
		if _, exists := seen[actionName]; exists {
			continue
		}
		seen[actionName] = struct{}{}

		existing, err := h.groupRepo.FindAction(groupName, actionName)
		if err != nil {
			logger.Warnf("Failed to check reported action: group=%s, action=%s, err=%v", groupName, actionName, err)
			continue
		}
		if existing != nil {
			continue
		}

		action := model.GroupAction{
			GroupName:  groupName,
			ActionName: actionName,
			CreateDate: time.Now(),
		}
		if err := h.groupRepo.CreateAction(&action); err != nil {
			logger.Warnf("Failed to create reported action: group=%s, action=%s, err=%v", groupName, actionName, err)
			continue
		}
		logger.Debugf("Reported action created: group=%s, action=%s", groupName, actionName)
	}
}

// handleInvokeStream handles a streaming invoke response chunk.
func (h *Handler) handleInvokeStream(msg *RpcMessage) {
	sequence := msg.GetSequence()
	if sequence == "" {
		logger.Warnf("Invoke stream chunk missing sequence number")
		return
	}

	requestTraceID := msg.TraceID
	if requestTraceID == "" {
		if record := h.timeoutManager.GetStream(sequence); record != nil {
			requestTraceID = record.TraceID
		}
	}
	chunk := &forwarder.StreamChunk{
		Data:    msg.Data,
		Error:   msg.Error,
		Status:  msg.Status,
		Done:    msg.Done,
		TraceID: requestTraceID,
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

			if sc.IsRegisteredGroup() && h.groupRepo != nil {
				if err := h.groupRepo.UpdateDeviceLastActive(msg.Group, msg.ClientID, time.Now()); err != nil {
					logger.Warnf("Failed to update device last_active_time: %v", err)
				}
			}
		}
	}

	response := RpcMessage{
		Type:      MessageTypeHeartbeat,
		Timestamp: time.Now().UnixMilli(),
	}
	if err := h.sendMessage(sekiroClient, &response); err != nil {
		logger.Debugf("Failed to send heartbeat response: %v", err)
	}
}

// handleInvokeResponse handles invoke response messages
func (h *Handler) handleInvokeResponse(msg *RpcMessage, rawData []byte) {
	sequence := msg.GetSequence()
	if sequence == "" {
		logger.Warnf("Invoke response missing sequence number")
		return
	}

	requestTraceID := msg.TraceID
	if requestTraceID == "" {
		if record := h.timeoutManager.Get(sequence); record != nil {
			requestTraceID = record.TraceID
		}
	}
	requestLogger := logger.WithTraceID(requestTraceID)

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
		requestLogger.Debugf("Invoke response with empty data but status>=0, handler may have returned object: sequence=%s", sequence)
	}

	requestLogger.Debugf("Invoke response received: sequence=%s, status=%d, Error=%s", sequence, msg.Status, errorMessage)

	response := &forwarder.InvokeResponse{
		Data:    responseData,
		Error:   errorMessage,
		Status:  msg.Status,
		TraceID: requestTraceID,
	}

	if sc := h.clientManager.GetClient(msg.Group, msg.ClientID); sc != nil {
		if msg.Status >= 0 {
			sc.MarkSuccess()
		} else {
			sc.MarkFailure()
		}
	}

	if !h.timeoutManager.Complete(sequence, response) {
		requestLogger.Debugf("Invoke response for expired request: sequence=%s", sequence)
	}
}

// sendMessage sends a message to the client via its transport connection.
func (h *Handler) sendMessage(sekiroClient *client.RpcClient, msg *RpcMessage) error {
	data, err := json.Marshal(msg)
	if err != nil {
		logger.Errorf("Failed to marshal message: %v", err)
		return err
	}

	if sekiroClient == nil || sekiroClient.Connection == nil {
		err := errors.New("sendMessage called with nil client or connection")
		logger.Warnf("%v", err)
		return err
	}

	if err := sekiroClient.Connection.Send(data); err != nil {
		logger.Debugf("Failed to send message: %v", err)
		return err
	}
	return nil
}

// sendError sends an error message to the client
func (h *Handler) sendError(sekiroClient *client.RpcClient, errorMsg, sequence string) {
	msg := RpcMessage{
		Type:      "error",
		Error:     errorMsg,
		Sequence:  sequence,
		Timestamp: time.Now().UnixMilli(),
	}
	if err := h.sendMessage(sekiroClient, &msg); err != nil {
		logger.Debugf("Failed to send error response: %v", err)
	}
}

// SendInvokeRequest sends an invoke request to a client.
// The transport connection is obtained from the RpcClient.
func (h *Handler) SendInvokeRequest(sekiroClient *client.RpcClient, sequence, group, clientID string, data []byte, traceID string) error {
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
	if traceID != "" {
		fullMsg["trace_id"] = traceID
	}
	for k, v := range msgData {
		fullMsg[k] = v
	}

	msgDataJSON, err := json.Marshal(fullMsg)
	if err != nil {
		logger.Errorf("Failed to marshal message: %v", err)
		return err
	}

	requestLogger := logger.WithTraceID(traceID)
	requestLogger.Debugf("Sending invoke message: sequence=%s, group=%s, clientId=%s", sequence, group, clientID)

	if sekiroClient == nil || sekiroClient.Connection == nil {
		requestLogger.Debugf("Invoke send failed: sequence=%s, err=invalid client connection", sequence)
		return errors.New("invalid client connection")
	}

	// Pre-send liveness probe: catch zombie connections (TCP half-open) before committing to the send.
	// Without this, Send() may succeed (OS TCP buffer) but the client never receives the message,
	// causing a 30s invoke timeout. The PingProbe fails fast (~3s) on dead connections.
	if wsConn, ok := sekiroClient.Connection.(*transport.WSConnection); ok {
		if err := wsConn.PingProbe(); err != nil {
			requestLogger.Warnf("Pre-send ping probe failed: group=%s, clientId=%s, err=%v", group, clientID, err)
			return fmt.Errorf("connection probe failed: %w", err)
		}
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
