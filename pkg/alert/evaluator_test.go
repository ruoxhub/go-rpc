package alert

import (
	"context"
	"runtime"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestCheckThreshold_AllOperators(t *testing.T) {
	e := &Evaluator{}
	tests := []struct {
		name      string
		value     float64
		operator  string
		threshold float64
		expected  bool
	}{
		{"gt_true", 10, ">", 5, true},
		{"gt_false", 3, ">", 5, false},
		{"lt_true", 3, "<", 5, true},
		{"lt_false", 10, "<", 5, false},
		{"gte_equal", 5, ">=", 5, true},
		{"gte_greater", 6, ">=", 5, true},
		{"gte_less", 4, ">=", 5, false},
		{"lte_equal", 5, "<=", 5, true},
		{"eq_true", 5, "==", 5, true},
		{"eq_false", 5.1, "==", 5, false},
		{"neq_true", 5.1, "!=", 5, true},
		{"neq_false", 5, "!=", 5, false},
		{"unknown", 5, "??", 5, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.expected, e.checkThreshold(tt.value, tt.operator, tt.threshold))
		})
	}
}

func TestEvaluator_StartStop(t *testing.T) {
	before := runtime.NumGoroutine()
	e := NewEvaluator(100*time.Millisecond, nil)
	e.Start(context.Background())
	time.Sleep(200 * time.Millisecond)
	e.Stop()
	time.Sleep(200 * time.Millisecond)
	assert.LessOrEqual(t, runtime.NumGoroutine(), before+2)
}
