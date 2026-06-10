package handler

import (
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/client"
)

func TestBuildAnonymousGroupVOsUsesMemoryOnly(t *testing.T) {
	manager := client.NewClientManager()

	online := client.NewRpcClient("anon-group", "online", nil)
	online.SetStatus(client.StatusOnline)
	manager.Register(online)

	inactive := client.NewRpcClient("anon-group", "inactive", nil)
	inactive.SetStatus(client.StatusOnline)
	inactive.LastActive = time.Now().Add(-ClientInactiveThreshold - time.Minute)
	manager.Register(inactive)

	registered := client.NewRpcClient("registered-group", "registered", nil)
	registered.SetStatus(client.StatusOnline)
	registered.SetRegisteredGroup(true)
	manager.Register(registered)

	vos := buildAnonymousGroupVOs(manager)
	if len(vos) != 1 {
		t.Fatalf("expected one anonymous group, got %d: %#v", len(vos), vos)
	}

	got := vos[0]
	if got.GroupName != "anon-group" {
		t.Fatalf("expected anon-group, got %s", got.GroupName)
	}
	if got.AvailableClients != 1 {
		t.Fatalf("expected 1 available client, got %d", got.AvailableClients)
	}
	if got.DisabledClients != 1 {
		t.Fatalf("expected 1 disabled client, got %d", got.DisabledClients)
	}
	if got.TotalClients != 2 {
		t.Fatalf("expected 2 total clients, got %d", got.TotalClients)
	}
}
