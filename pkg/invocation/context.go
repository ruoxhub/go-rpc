package invocation

import (
	"time"

	"github.com/mrh30000/go-rpc/pkg/protocol"
)

type Context struct {
	sequence       string
	traceID        string
	group          string
	action         string
	clientID       string
	deadline       time.Time
	idempotent     bool
	idempotencyKey string
	attempt        int
}

func New(sequence, traceID, group, action, clientID string, deadline time.Time) Context {
	return Context{
		sequence: sequence, traceID: traceID, group: group, action: action,
		clientID: clientID, deadline: deadline, attempt: 1,
	}
}

func (c Context) Wire() protocol.WireInvocationContext {
	return protocol.WireInvocationContext{
		Sequence:       c.sequence,
		TraceID:        c.traceID,
		Group:          c.group,
		Action:         c.action,
		ClientID:       c.clientID,
		DeadlineUnixMS: c.deadline.UnixMilli(),
		Idempotent:     c.idempotent,
		IdempotencyKey: c.idempotencyKey,
		Attempt:        c.attempt,
	}
}
