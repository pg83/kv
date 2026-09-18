package main

import (
	"fmt"
	"net/http"
	"sort"
	"strings"
	"sync"
	"time"
)

var latencyBounds = [...]float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5}

type RequestMetrics struct {
	count   uint64
	seconds float64
	buckets [len(latencyBounds)]uint64
}

type Metrics struct {
	mu       sync.Mutex
	requests map[string]RequestMetrics
}

type MetricsResponse struct {
	http.ResponseWriter
	status int
}

type BucketMetrics struct {
	name   string
	values [8]float64
}

func newMetrics() *Metrics {
	return &Metrics{requests: map[string]RequestMetrics{}}
}

func (w *MetricsResponse) WriteHeader(status int) {
	w.writeHeader(status)
}

func (w *MetricsResponse) writeHeader(status int) {
	w.status = status
	w.ResponseWriter.WriteHeader(status)
}

func (m *Metrics) track(scope, operation string, cb http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, request *http.Request) {
		start := time.Now()
		response := &MetricsResponse{ResponseWriter: w, status: http.StatusOK}

		cb(response, request)
		m.observe(scope, operation, response.status, time.Since(start).Seconds())
	}
}

func (m *Metrics) observe(scope, operation string, status int, seconds float64) {
	labels := fmt.Sprintf("scope=%q,operation=%q,code=%q", scope, operation, fmt.Sprint(status))

	m.mu.Lock()

	defer m.mu.Unlock()

	metric := m.requests[labels]

	metric.count++
	metric.seconds += seconds

	for i, bound := range latencyBounds {
		if seconds <= bound {
			metric.buckets[i]++
		}
	}

	m.requests[labels] = metric
}

func (m *Metrics) snapshot() map[string]RequestMetrics {
	m.mu.Lock()

	defer m.mu.Unlock()

	values := make(map[string]RequestMetrics, len(m.requests))

	for labels, value := range m.requests {
		values[labels] = value
	}

	return values
}

func (s *Store) metrics() []BucketMetrics {
	values := make([]BucketMetrics, 0, len(s.buckets))

	for name, bucket := range s.buckets {
		bucket.mu.Lock()

		values = append(values, BucketMetrics{name: name, values: [8]float64{
			float64(bucket.capacity), float64(bucket.size), float64(len(bucket.items)),
			float64(bucket.hits), float64(bucket.misses), float64(bucket.puts),
			float64(bucket.evicted), float64(bucket.rejected),
		}})

		bucket.mu.Unlock()
	}

	sort.Slice(values, func(i, j int) bool { return values[i].name < values[j].name })

	return values
}

func metricHeader(out *strings.Builder, name, kind, help string) {
	fmt.Fprintf(out, "# HELP %s %s\n# TYPE %s %s\n", name, help, name, kind)
}

func metricLabel(value string) string {
	return "\"" + strings.NewReplacer("\\", "\\\\", "\"", "\\\"", "\n", "\\n").Replace(value) + "\""
}

func (m *Metrics) serve(w http.ResponseWriter, store *Store) {
	var out strings.Builder

	requests := m.snapshot()
	labels := make([]string, 0, len(requests))

	for label := range requests {
		labels = append(labels, label)
	}

	sort.Strings(labels)
	metricHeader(&out, "kv_http_requests_total", "counter", "Completed KV API requests by scope, operation and response code.")

	for _, label := range labels {
		fmt.Fprintf(&out, "kv_http_requests_total{%s} %d\n", label, requests[label].count)
	}

	metricHeader(&out, "kv_http_request_duration_seconds", "histogram", "KV API request duration including forwarding.")

	for _, label := range labels {
		metric := requests[label]

		for i, bound := range latencyBounds {
			fmt.Fprintf(&out, "kv_http_request_duration_seconds_bucket{%s,le=\"%g\"} %d\n", label, bound, metric.buckets[i])
		}

		fmt.Fprintf(&out, "kv_http_request_duration_seconds_bucket{%s,le=\"+Inf\"} %d\n", label, metric.count)
		fmt.Fprintf(&out, "kv_http_request_duration_seconds_sum{%s} %g\n", label, metric.seconds)
		fmt.Fprintf(&out, "kv_http_request_duration_seconds_count{%s} %d\n", label, metric.count)
	}

	if store != nil {
		store.writeMetrics(&out)
	}

	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	writeHeader(w, http.StatusOK)

	_, _ = chaosCall2("write response", func() (int, error) {
		return w.Write([]byte(out.String()))
	})
}

func (s *Store) writeMetrics(out *strings.Builder) {
	buckets := s.metrics()

	families := [][3]string{
		{"kv_bucket_capacity_bytes", "gauge", "Configured local bucket capacity in key and value bytes."},
		{"kv_bucket_bytes", "gauge", "Local bucket key and value bytes, excluding storage overhead."},
		{"kv_bucket_items", "gauge", "Number of entries in the local bucket."},
		{"kv_bucket_hits_total", "counter", "Local lookups that found a value."},
		{"kv_bucket_misses_total", "counter", "Local lookups that did not find a value."},
		{"kv_bucket_puts_total", "counter", "Successful local writes including replacements."},
		{"kv_bucket_evictions_total", "counter", "Entries evicted to satisfy the local capacity limit."},
		{"kv_bucket_rejected_puts_total", "counter", "Local writes rejected because the entry exceeded capacity."},
	}

	for i, family := range families {
		metricHeader(out, family[0], family[1], family[2])

		for _, bucket := range buckets {
			fmt.Fprintf(out, "%s{bucket=%s} %g\n", family[0], metricLabel(bucket.name), bucket.values[i])
		}
	}
}
