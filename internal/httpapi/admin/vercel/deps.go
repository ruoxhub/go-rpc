package vercel

import (
	"github.com/mrh30000/go-rpc/internal/chathistory"
	adminshared "github.com/mrh30000/go-rpc/internal/httpapi/admin/shared"
)

type Handler struct {
	Store       adminshared.ConfigStore
	Pool        adminshared.PoolController
	DS          adminshared.DeepSeekCaller
	OpenAI      adminshared.OpenAIChatCaller
	ChatHistory *chathistory.Store
}

var writeJSON = adminshared.WriteJSON
var intFrom = adminshared.IntFrom

func nilIfZero(v int64) any     { return adminshared.NilIfZero(v) }
func statusOr(v int, d int) int { return adminshared.StatusOr(v, d) }

func (h *Handler) computeSyncHash() string {
	return adminshared.ComputeSyncHash(h.Store)
}
