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

	// Fuzzy=true：仅走模糊匹配（健康优先），与重构前语义一致
	if params.Fuzzy {
		return group.FindClientByFuzzy(params.ClientID)
	}

	// 精确匹配（GetClient 不按健康过滤，与重构前一致）
	return group.GetClient(params.ClientID)
}
