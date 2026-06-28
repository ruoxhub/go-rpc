package router

import (
	"github.com/mrh30000/go-rpc/pkg/client"
)

// SpecifiedStrategy 指定客户端策略（精确匹配 + 模糊匹配）
type SpecifiedStrategy struct{}

// Select 根据 ClientID 选择客户端
func (s *SpecifiedStrategy) Select(group *client.RpcGroup, params RouteParams) *client.RpcClient {
	if params.ClientID == "" {
		return nil
	}

	// 精确匹配
	if c := group.GetClient(params.ClientID); c != nil {
		return c
	}

	// 模糊匹配（Fuzzy=true）
	if params.Fuzzy {
		return group.FindClientByFuzzy(params.ClientID)
	}

	return nil
}
