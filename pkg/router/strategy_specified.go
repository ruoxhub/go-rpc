package router

import (
	"math/rand"
	"strings"

	"github.com/mrh30000/go-rpc/pkg/client"
)

// SpecifiedStrategy 指定客户端策略（精确匹配 + 模糊匹配）
type SpecifiedStrategy struct{}

// Select 根据 ClientID 选择客户端
func (s *SpecifiedStrategy) Select(group *client.RpcGroup, params RouteParams) *client.RpcClient {
	if params.ClientID == "" {
		return nil
	}

	// Fuzzy=true：走模糊匹配（健康优先）
	if params.Fuzzy {
		if params.ExecutorType == "" {
			return group.FindClientByFuzzy(params.ClientID)
		}
		return findFuzzyWithExecutorType(group, params.ClientID, params.ExecutorType)
	}

	// 精确匹配
	selected := group.GetClient(params.ClientID)
	if selected == nil {
		return nil
	}
	if params.ExecutorType != "" && selected.GetExecutorType() != params.ExecutorType {
		return nil
	}
	return selected
}

func findFuzzyWithExecutorType(group *client.RpcGroup, substr, executorType string) *client.RpcClient {
	clients := group.GetAllClients()
	var healthy []*client.RpcClient
	var online []*client.RpcClient

	for _, c := range clients {
		if !strings.Contains(c.ClientID, substr) {
			continue
		}
		if executorType != "" && c.GetExecutorType() != executorType {
			continue
		}
		if c.GetStatus() != client.StatusOnline {
			continue
		}
		online = append(online, c)
		if c.GetHealthStatus() {
			healthy = append(healthy, c)
		}
	}

	if len(healthy) > 0 {
		return healthy[rand.Intn(len(healthy))]
	}
	if len(online) > 0 {
		return online[rand.Intn(len(online))]
	}
	return nil
}
