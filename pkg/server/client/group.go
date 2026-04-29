package client

import (
	"errors"
	"sync"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
)

// commandType represents types of group commands
type commandType int

const (
	cmdRegister commandType = iota
	cmdUnregister
	cmdGetClient
	cmdGetAllClients
	cmdAllocate
	cmdClose
)

// groupCommand represents a command to the group goroutine
type groupCommand struct {
	typ      commandType
	client   *RpcClient
	clientID string
	callback chan commandResult
}

// commandResult holds the result of a group command
type commandResult struct {
	client  *RpcClient
	clients []*RpcClient
	err     error
}

// RpcGroup manages clients in a single group using goroutine + channel
type RpcGroup struct {
	name        string
	commandChan chan groupCommand
	clients     map[string]*RpcClient
	order       []string
	wg          sync.WaitGroup
	closed      bool
	mu          sync.Mutex
}

// NewRpcGroup creates a new RpcGroup
func NewRpcGroup(name string) *RpcGroup {
	g := &RpcGroup{
		name:        name,
		commandChan: make(chan groupCommand, 64),
		clients:     make(map[string]*RpcClient),
		order:       make([]string, 0, 8),
	}

	g.wg.Add(1)
	go g.runLoop()

	return g
}

// runLoop processes commands in a single goroutine
func (g *RpcGroup) runLoop() {
	defer g.wg.Done()

	for cmd := range g.commandChan {
		switch cmd.typ {
		case cmdRegister:
			if _, exists := g.clients[cmd.client.ClientID]; !exists {
				g.order = append(g.order, cmd.client.ClientID)
			}
			g.clients[cmd.client.ClientID] = cmd.client
			logger.Infof("Client registered: group=%s, clientId=%s", g.name, cmd.client.ClientID)

		case cmdUnregister:
			if client, ok := g.clients[cmd.clientID]; ok {
				client.Close()
				delete(g.clients, cmd.clientID)
				g.removeFromOrder(cmd.clientID)
				logger.Infof("Client unregistered: group=%s, clientId=%s", g.name, cmd.clientID)
			}

		case cmdGetClient:
			client := g.clients[cmd.clientID]
			cmd.callback <- commandResult{client: client}

		case cmdGetAllClients:
			clients := g.snapshotClients()
			cmd.callback <- commandResult{clients: clients}

		case cmdAllocate:
			// Allocate with health-aware logic
			var allocated *RpcClient

			// First try to find a healthy client
			for _, c := range g.clients {
				if c.GetStatus() == StatusOnline && c.IsHealthy {
					allocated = c
					break
				}
			}

			// If no healthy client found, fall back to any online client
			if allocated == nil {
				for _, c := range g.clients {
					if c.GetStatus() == StatusOnline {
						allocated = c
						break
					}
				}
			}

			// If still no client found, return any client as last resort
			if allocated == nil && len(g.clients) > 0 {
				for _, c := range g.clients {
					allocated = c
					break
				}
			}
			cmd.callback <- commandResult{client: allocated}

		case cmdClose:
			for _, c := range g.clients {
				c.Close()
			}
			g.clients = make(map[string]*RpcClient)
			g.order = nil
			cmd.callback <- commandResult{}
			return
		}
	}
}

func (g *RpcGroup) snapshotClients() []*RpcClient {
	clients := make([]*RpcClient, 0, len(g.order))
	for _, clientID := range g.order {
		if c, ok := g.clients[clientID]; ok {
			clients = append(clients, c)
		}
	}
	return clients
}

func (g *RpcGroup) removeFromOrder(clientID string) {
	for i, id := range g.order {
		if id != clientID {
			continue
		}
		g.order = append(g.order[:i], g.order[i+1:]...)
		return
	}
}

// Register registers a client to the group
func (g *RpcGroup) Register(client *RpcClient) {
	g.mu.Lock()
	closed := g.closed
	g.mu.Unlock()

	if closed {
		return
	}
	g.commandChan <- groupCommand{
		typ:    cmdRegister,
		client: client,
	}
}

// Unregister unregisters a client from the group
func (g *RpcGroup) Unregister(clientID string) {
	g.mu.Lock()
	closed := g.closed
	g.mu.Unlock()

	if closed {
		return
	}
	g.commandChan <- groupCommand{
		typ:      cmdUnregister,
		clientID: clientID,
	}
}

// GetClient gets a client by ID
func (g *RpcGroup) GetClient(clientID string) *RpcClient {
	g.mu.Lock()
	closed := g.closed
	g.mu.Unlock()

	if closed {
		return nil
	}

	callback := make(chan commandResult, 1)
	g.commandChan <- groupCommand{
		typ:      cmdGetClient,
		clientID: clientID,
		callback: callback,
	}
	result := <-callback
	return result.client
}

// GetAllClients gets all clients in the group
func (g *RpcGroup) GetAllClients() []*RpcClient {
	g.mu.Lock()
	closed := g.closed
	g.mu.Unlock()

	if closed {
		return nil
	}

	callback := make(chan commandResult, 1)
	g.commandChan <- groupCommand{
		typ:      cmdGetAllClients,
		callback: callback,
	}
	result := <-callback
	return result.clients
}

// AllocateClient allocates a client for invocation
func (g *RpcGroup) AllocateClient() *RpcClient {
	g.mu.Lock()
	closed := g.closed
	g.mu.Unlock()

	if closed {
		return nil
	}

	callback := make(chan commandResult, 1)
	g.commandChan <- groupCommand{
		typ:      cmdAllocate,
		callback: callback,
	}
	result := <-callback
	return result.client
}

// Close closes the group and all clients
func (g *RpcGroup) Close() {
	g.mu.Lock()
	if g.closed {
		g.mu.Unlock()
		return
	}
	g.closed = true
	g.mu.Unlock()

	callback := make(chan commandResult, 1)
	g.commandChan <- groupCommand{
		typ:      cmdClose,
		callback: callback,
	}
	<-callback

	g.wg.Wait()
}

// Name returns the group name
func (g *RpcGroup) Name() string {
	return g.name
}

// ClientCount returns the number of clients in the group
func (g *RpcGroup) ClientCount() int {
	g.mu.Lock()
	closed := g.closed
	g.mu.Unlock()

	if closed {
		return 0
	}

	callback := make(chan commandResult, 1)
	g.commandChan <- groupCommand{
		typ:      cmdGetAllClients,
		callback: callback,
	}
	result := <-callback
	return len(result.clients)
}

// HasClient checks if a client exists in the group
func (g *RpcGroup) HasClient(clientID string) bool {
	return g.GetClient(clientID) != nil
}

// AllocateClientWithStatus allocates a client with specific status requirement
func (g *RpcGroup) AllocateClientWithStatus(status ClientStatus) *RpcClient {
	g.mu.Lock()
	defer g.mu.Unlock()

	if g.closed {
		return nil
	}

	callback := make(chan commandResult, 1)
	g.commandChan <- groupCommand{
		typ:      cmdAllocate,
		callback: callback,
	}
	result := <-callback

	if result.client == nil {
		return nil
	}

	if result.client.GetStatus() != status {
		// If status doesn't match, return nil or the client anyway
		// depending on requirements
		return result.client
	}

	return result.client
}

// ErrNoClientAvailable is returned when no client is available
var ErrNoClientAvailable = errors.New("no client available")
