package alert

import (
	"errors"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/stretchr/testify/assert"
)

type mockMetricStore struct {
	points  []repository.MetricMinutePoint
	mapping *repository.MetricTagMapping
	err     error
}

func (m *mockMetricStore) FlushMinutes(_ []model.MetricMinute) error { return nil }
func (m *mockMetricStore) UpsertMetricTag(_, _, _, _ string) error   { return nil }
func (m *mockMetricStore) RollupHours(_ string) error                { return nil }
func (m *mockMetricStore) RollupDays(_ string) error                 { return nil }
func (m *mockMetricStore) DeleteExpired(_ string, _ time.Time) error { return nil }
func (m *mockMetricStore) QueryMetricMinutes(_ string, _ map[string]string, _ *repository.MetricTagMapping, _ int) ([]repository.MetricMinutePoint, error) {
	return m.points, m.err
}
func (m *mockMetricStore) LoadMetricTagMapping(_ string) (*repository.MetricTagMapping, error) {
	return m.mapping, m.err
}

func TestRepoMetricQueryStore_QueryMetricMinutes(t *testing.T) {
	mock := &mockMetricStore{
		points: []repository.MetricMinutePoint{
			{TimeKey: "202401011200", Value: 1.5},
			{TimeKey: "202401011201", Value: 2.5},
		},
	}
	adapter := &RepoMetricQueryStore{Inner: mock}

	points, err := adapter.QueryMetricMinutes("test", nil, nil, 10)
	assert.NoError(t, err)
	assert.Len(t, points, 2)
	assert.Equal(t, "202401011200", points[0].TimeKey)
	assert.Equal(t, 1.5, points[0].Value)
}

func TestRepoMetricQueryStore_LoadMetricTagMapping(t *testing.T) {
	mock := &mockMetricStore{
		mapping: &repository.MetricTagMapping{
			Tag1Name: "group",
			Tag2Name: "api",
		},
	}
	adapter := &RepoMetricQueryStore{Inner: mock}

	mapping, err := adapter.LoadMetricTagMapping("test")
	assert.NoError(t, err)
	assert.NotNil(t, mapping)
	assert.Equal(t, "group", mapping.Tag1Name)
	assert.Equal(t, "api", mapping.Tag2Name)
}

func TestRepoMetricQueryStore_LoadMetricTagMapping_NotFound(t *testing.T) {
	mock := &mockMetricStore{mapping: nil}
	adapter := &RepoMetricQueryStore{Inner: mock}

	mapping, err := adapter.LoadMetricTagMapping("missing")
	assert.NoError(t, err)
	assert.Nil(t, mapping)
}

func TestRepoMetricQueryStore_Error(t *testing.T) {
	mock := &mockMetricStore{err: errors.New("db error")}
	adapter := &RepoMetricQueryStore{Inner: mock}

	_, err := adapter.QueryMetricMinutes("test", nil, nil, 10)
	assert.Error(t, err)

	_, err = adapter.LoadMetricTagMapping("test")
	assert.Error(t, err)
}

func TestRepoMetricQueryStore_WithTagMapping(t *testing.T) {
	mock := &mockMetricStore{
		points: []repository.MetricMinutePoint{{TimeKey: "t1", Value: 3.0}},
	}
	adapter := &RepoMetricQueryStore{Inner: mock}

	tagMapping := &MetricTagMapping{
		Tag1Name: "group",
		Tag2Name: "api",
	}
	tags := map[string]string{"group": "g1", "api": "/invoke"}

	points, err := adapter.QueryMetricMinutes("test", tags, tagMapping, 5)
	assert.NoError(t, err)
	assert.Len(t, points, 1)
}
