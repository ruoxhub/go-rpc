package configmgmt

import (
	"testing"

	"github.com/mrh30000/go-rpc/internal/account"
	"github.com/mrh30000/go-rpc/internal/config"
)

func newAdminTestHandler(t *testing.T, raw string) *Handler {
	t.Helper()
	t.Setenv("DS2API_CONFIG_JSON", raw)
	store := config.LoadStore()
	return &Handler{
		Store: store,
		Pool:  account.NewPool(store),
	}
}
