package metrics

import "testing"

func TestToMetricRecordsUsesDotPercentileNaming(t *testing.T) {
	c := &collector{}
	bucket := &metricBucket{
		Name:    "invoke.latency",
		TimeKey: "202604251000",
		Tags: map[string]string{
			"group": "g1",
			"api":   "a1",
		},
		Type:  MetricTypeHistogram,
		Value: 123,
	}

	records := c.toMetricRecords(bucket, map[float64]float64{
		50: 1,
		90: 2,
		99: 3,
	})

	names := map[string]bool{}
	for _, record := range records {
		names[record.Name] = true
	}

	if !names["invoke.latency.p50"] || !names["invoke.latency.p90"] || !names["invoke.latency.p99"] {
		t.Fatalf("unexpected percentile names: %+v", names)
	}
}
