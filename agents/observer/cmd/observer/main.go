package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/google/generative-ai-go/genai"
	"github.com/streadway/amqp"
	"google.golang.org/api/option"
)

// =====================================================================================
// Core Data Structures
// =====================================================================================

type ObserverData struct {
	Cluster          string                  `json:"cluster"`
	Timestamp        time.Time               `json:"timestamp"`
	AggregateMetrics map[string]MetricSnapshot `json:"aggregate_metrics"`
	SignificantLogs  []LogEntry              `json:"significant_logs"`
}

type PodInfo struct {
	Name      string `json:"name"`
	Namespace string `json:"namespace"`
	Status    string `json:"status"`
}

type ServiceInfo struct {
	Name      string `json:"name"`
	Namespace string `json:"namespace"`
}

type LogEntry struct {
	Timestamp time.Time `json:"timestamp"`
	Message   string    `json:"message"`
	Service   string    `json:"service"` // The 'job' from Loki
	Level     string    `json:"level"`
}

type CommitInfo struct {
	SHA       string    `json:"sha"`
	Message   string    `json:"message"`
	Author    string    `json:"author"`
	Timestamp time.Time `json:"timestamp"`
}

type Config struct {
	RabbitMQURL      string
	PrometheusURL    string
	LokiURL          string
	LokiLogWindow    string
	GeminiAPIKey     string
	ClusterName      string
	AlertInterval    int
	CPUThreshold     float64
	ErrorThreshold   float64
	LatencyThreshold float64
	LLMModelName     string
	LLMMaxLogs       int // Max number of logs to send to the LLM
	LLMMaxLogLength  int // Max characters per log message
}

// =====================================================================================
// Prometheus Collector
// =====================================================================================

type PrometheusCollector struct {
	baseURL string
	client  *http.Client
}

type MetricSnapshot struct {
	ErrorRate      float64 `json:"error_rate_percent"`
	LatencyP95     float64 `json:"latency_p95_seconds"`
	TrafficReqPerSec float64 `json:"traffic_req_per_sec"`
	CpuUsageCores  float64 `json:"cpu_usage_cores"`
}

func NewPrometheusCollector(config *Config) *PrometheusCollector {
	return &PrometheusCollector{
		baseURL: config.PrometheusURL,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (p *PrometheusCollector) CollectKeyMetrics(ctx context.Context) (map[string]MetricSnapshot, error) {
	allMetrics := make(map[string]MetricSnapshot)
	queries := map[string]string{
		"error_rate":      `sum(rate(http_requests_total{job!="", code=~"5.*"}[5m])) by (job) / sum(rate(http_requests_total{job!=""}[5m])) by (job) * 100`,
		"latency_p95":     `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job!=""}[5m])) by (le, job))`,
		"traffic_req_sec": `sum(rate(http_requests_total{job!=""}[5m])) by (job)`,
		"cpu_usage_cores": `sum(rate(container_cpu_usage_seconds_total{image!="", job!=""}[5m])) by (job)`,
	}

	merge := func(metricType string, data map[string]float64) {
		for service, value := range data {
			snapshot := allMetrics[service]
			switch metricType {
			case "error_rate": snapshot.ErrorRate = value
			case "latency_p95": snapshot.LatencyP95 = value
			case "traffic_req_sec": snapshot.TrafficReqPerSec = value
			case "cpu_usage_cores": snapshot.CpuUsageCores = value
			}
			allMetrics[service] = snapshot
		}
	}

	for metricType, query := range queries {
		vectorData, err := p.queryVector(ctx, query)
		if err != nil {
			log.Printf("Warning: failed to query metric type '%s': %v", metricType, err)
			continue
		}
		merge(metricType, vectorData)
	}
	return allMetrics, nil
}

// queryLokiVector is a helper to query Loki for vector results, similar to Prometheus.
// Note the slightly different API endpoint: /loki/api/v1/query
func (p *PrometheusCollector) queryLokiVector(ctx context.Context, query string) (map[string]float64, error) {
	params := url.Values{}
	params.Set("query", query)
	reqUrl := fmt.Sprintf("%s/loki/api/v1/query?%s", p.baseURL, params.Encode())
	req, err := http.NewRequestWithContext(ctx, "GET", reqUrl, nil)
	if err != nil {
		return nil, err
	}

	resp, err := p.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("loki vector query failed with status %d: %s", resp.StatusCode, string(body))
	}

	var result struct {
		Data struct {
			Result []struct {
				Metric map[string]string `json:"metric"`
				Value  []interface{}     `json:"value"`
			} `json:"result"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("failed to unmarshal loki vector response: %w", err)
	}

	dataMap := make(map[string]float64)
	for _, res := range result.Data.Result {
		jobName, ok := res.Metric["job"]
		if !ok {
			continue
		}
		if len(res.Value) < 2 {
			continue
		}
		valueStr, ok := res.Value[1].(string)
		if !ok {
			continue
		}
		value, err := strconv.ParseFloat(valueStr, 64)
		if err != nil {
			continue
		}
		dataMap[jobName] = value
	}
	return dataMap, nil
}

func (p *PrometheusCollector) queryVector(ctx context.Context, query string) (map[string]float64, error) {
	params := url.Values{}
	params.Set("query", query)
	reqUrl := fmt.Sprintf("%s/api/v1/query?%s", p.baseURL, params.Encode())
	req, err := http.NewRequestWithContext(ctx, "GET", reqUrl, nil)
	if err != nil { return nil, err }

	resp, err := p.client.Do(req)
	if err != nil { return nil, err }
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil { return nil, err }

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("prometheus query failed with status %d: %s", resp.StatusCode, string(body))
	}

	var result struct {
		Data struct {
			Result []struct {
				Metric map[string]string `json:"metric"`
				Value  []interface{}     `json:"value"`
			} `json:"result"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("failed to unmarshal prometheus response: %w", err)
	}

	dataMap := make(map[string]float64)
	for _, res := range result.Data.Result {
		jobName, ok := res.Metric["job"]
		if !ok { continue }
		if len(res.Value) < 2 { continue }
		valueStr, ok := res.Value[1].(string)
		if !ok { continue }
		value, err := strconv.ParseFloat(valueStr, 64)
		if err != nil { continue }
		dataMap[jobName] = value
	}
	return dataMap, nil
}

// =====================================================================================
// Loki Collector
// =====================================================================================

// LogStats holds the count of logs by severity for a service.
type LogStats struct {
	ErrorCount    float64
	WarningCount  float64
	CriticalCount float64
}

type LokiCollector struct {
	baseURL string
	client  *http.Client
}

func NewLokiCollector(config *Config) *LokiCollector {
	return &LokiCollector{
		baseURL: config.LokiURL,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (l *LokiCollector) CollectSignificantLogs(ctx context.Context, lookbackMinutes int, limit int, servicesOfInterest []string) ([]LogEntry, error) {
	var query string
	// If we have specific services, build a targeted query. Otherwise, search globally.
	if len(servicesOfInterest) > 0 {
		servicePattern := strings.Join(servicesOfInterest, "|")
		query = fmt.Sprintf(`{job=~"%s"} |~ "(?i)error|warn|fatal|exception|panic"`, servicePattern)
		log.Printf("Collecting logs for anomalous services: %v", servicesOfInterest)
	} else {
		query = `{job=~"_+"} |~ "(?i)error|warn|fatal|exception|panic"`
		log.Println("No anomalous services detected, collecting all significant logs.")
	}

	end := time.Now()
	start := end.Add(-time.Duration(lookbackMinutes) * time.Minute)

	logs, err := l.queryLogs(ctx, query, start, end, limit)
	if err != nil {
		// The error is already logged in queryLogs, just return it
		return nil, fmt.Errorf("failed to query logs: %w", err)
	}

	log.Printf("Found %d significant log entries.", len(logs))
	return logs, nil
}

func (l *LokiCollector) GetLogStatsByService(ctx context.Context, lookbackMinutes int) (map[string]LogStats, error) {
	statsByService := make(map[string]LogStats)

	// Define queries to count logs by severity, grouped by the 'job' label (service name).
	queries := map[string]string{
		"critical": fmt.Sprintf(`sum by (job) (count_over_time({job!=""} |~ "(?i)critical|fatal" [%dm]))`, lookbackMinutes),
		"error":    fmt.Sprintf(`sum by (job) (count_over_time({job!=""} |~ "(?i)error|exception" [%dm]))`, lookbackMinutes),
		"warning":  fmt.Sprintf(`sum by (job) (count_over_time({job!=""} |~ "(?i)warn|warning" [%dm]))`, lookbackMinutes),
	}

	// This is a temporary simplification to reuse the logic from Prometheus's queryVector.
	// In a real app, you'd create a shared client or duplicate the queryVector logic.
	queryFunc := func(query string) (map[string]float64, error) {
		tempPromCollector := &PrometheusCollector{baseURL: l.baseURL, client: l.client}
		// We adapt the URL for Loki's vector query endpoint.
		return tempPromCollector.queryLokiVector(ctx, query)
	}

	for level, query := range queries {
		results, err := queryFunc(query)
		if err != nil {
			log.Printf("Warning: failed to get log stats for level '%s': %v", level, err)
			continue
		}

		for service, count := range results {
			stats := statsByService[service]
			switch level {
			case "critical":
				stats.CriticalCount = count
			case "error":
				stats.ErrorCount = count
			case "warning":
				stats.WarningCount = count
			}
			statsByService[service] = stats
		}
	}

	return statsByService, nil
}

func (l *LokiCollector) queryLogs(ctx context.Context, query string, start, end time.Time, limit int) ([]LogEntry, error) {
	log.Printf("Querying Loki with query: %s", query)
	
	params := url.Values{}
	params.Set("query", query)
	params.Set("start", strconv.FormatInt(start.UnixNano(), 10))
	params.Set("end", strconv.FormatInt(end.UnixNano(), 10))
	params.Set("limit", strconv.Itoa(limit))
	params.Set("direction", "backward")

	reqUrl := fmt.Sprintf("%s/loki/api/v1/query_range?%s", l.baseURL, params.Encode())
	req, err := http.NewRequestWithContext(ctx, "GET", reqUrl, nil)
	if err != nil { 
		log.Printf("Error creating request: %v", err)
		return nil, err 
	}

	resp, err := l.client.Do(req)
	if err != nil { 
		log.Printf("Error executing request: %v", err)
		return nil, err 
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil { 
		log.Printf("Error reading response body: %v", err)
		return nil, err 
	}

	if resp.StatusCode != http.StatusOK {
		log.Printf("Loki API returned non-200 status: %d, response: %s", resp.StatusCode, string(body))
		return nil, fmt.Errorf("loki query failed with status %d: %s", resp.StatusCode, string(body))
	}

	var result struct {
		Data struct {
			Result []struct {
				Stream map[string]string `json:"stream"`
				Values [][]string        `json:"values"`
			} `json:"result"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("failed to unmarshal loki response: %w", err)
	}

	var logs []LogEntry
	seen := make(map[string]bool)
	for _, stream := range result.Data.Result {
		for _, value := range stream.Values {
			if len(value) != 2 { continue }
			timestampNs, err := strconv.ParseInt(value[0], 10, 64)
			if err != nil { continue }

			logEntry := LogEntry{
				Timestamp: time.Unix(0, timestampNs),
				Message:   value[1],
			}
			if job, ok := stream.Stream["job"]; ok { logEntry.Service = job }
			if level, ok := stream.Stream["level"]; ok { logEntry.Level = level }

			key := fmt.Sprintf("%d_%s_%s", logEntry.Timestamp.UnixNano(), logEntry.Service, logEntry.Message)
			if !seen[key] {
				logs = append(logs, logEntry)
				seen[key] = true
			}
		}
	}
	return logs, nil
}

// =====================================================================================
// LLM Summarizer with Context Limiting
// =====================================================================================

type LLMSummarizer struct {
	client    *genai.GenerativeModel
	modelName string
}

func NewLLMSummarizer(config *Config) (*LLMSummarizer, error) {
	if config.GeminiAPIKey == "" {
		log.Println("Warning: GEMINI_API_KEY is not set. LLMSummarizer will be disabled.")
		return &LLMSummarizer{client: nil, modelName: ""}, nil
	}

	ctx := context.Background()
	client, err := genai.NewClient(ctx, option.WithAPIKey(config.GeminiAPIKey))
	if err != nil {
		return nil, fmt.Errorf("failed to create Gemini client: %w", err)
	}
	
	model := client.GenerativeModel(config.LLMModelName)
	return &LLMSummarizer{client: model, modelName: config.LLMModelName}, nil
}

func (s *LLMSummarizer) Summarize(ctx context.Context, data *ObserverData) (string, error) {
	if s.client == nil {
		return `{"summary": "LLM summarization is disabled; API key not provided."}`, nil
	}
	if len(data.AggregateMetrics) == 0 && len(data.SignificantLogs) == 0 {
		return `{"summary": "No significant data to summarize."}`, nil
	}

	dataJSON, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return "", fmt.Errorf("failed to serialize data for LLM: %w", err)
	}

	prompt := fmt.Sprintf(`
You are an expert Kubernetes cluster observer. Analyze the provided metrics and logs to create a concise, non-repetitive analysis.

Data to analyze:
%s

CRITICAL INSTRUCTIONS:
1. Group similar log entries - do NOT repeat the same error message multiple times
2. Each service should have maximum 3 unique issues
3. Each issue should have maximum 2 representative log entries
4. Focus on DISTINCT problems, not repetitive entries
5. Provide ONE clear hypothesis per issue

Respond with valid JSON only (no extra text):
{
  "summary": "One sentence cluster health assessment",
  "health_score": <integer 0-100>,
  "service_analysis": {
    "<service-name>": {
      "key_metrics": {
        "error_rate_percent": <float or 0>,
        "latency_p95_seconds": <float or 0>,
        "traffic_req_per_sec": <float or 0>,
        "cpu_usage_cores": <float or 0>
      },
      "identified_issues": [
        {
          "issue": "Brief unique issue description",
          "log_evidences": [
            "Most relevant log entry 1",
            "Most relevant log entry 2"
          ],
          "hypothesis": "Single sentence root cause analysis"
        }
      ]
    }
  }
}

Health scoring: 90-100=Excellent, 70-89=Good, 50-69=Degraded, 30-49=Poor, 0-29=Critical
    `, string(dataJSON))

	log.Printf("Sending data to Gemini API (%s) for summarization...", s.modelName)
	resp, err := s.client.GenerateContent(ctx, genai.Text(prompt))
	if err != nil {
		return "", fmt.Errorf("failed to call Gemini API: %w", err)
	}

	if len(resp.Candidates) == 0 || resp.Candidates[0].Content == nil || len(resp.Candidates[0].Content.Parts) == 0 {
		return "", fmt.Errorf("gemini API returned no content")
	}

	part := resp.Candidates[0].Content.Parts[0]
	if txt, ok := part.(genai.Text); ok {
		return extractJSON(string(txt)), nil
	}

	return "", fmt.Errorf("unexpected response format from Gemini API")
}

func extractJSON(response string) string {
	start := strings.Index(response, "{")
	end := strings.LastIndex(response, "}")
	if start != -1 && end != -1 && end > start {
		return response[start : end+1]
	}
	return response
}

// =====================================================================================
// RabbitMQ Publisher
// =====================================================================================

type RabbitMQPublisher struct {
	conn    *amqp.Connection
	channel *amqp.Channel
}

func NewRabbitMQPublisher(config *Config) (*RabbitMQPublisher, error) {
	conn, err := amqp.Dial(config.RabbitMQURL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to RabbitMQ: %w", err)
	}

	channel, err := conn.Channel()
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("failed to open channel: %w", err)
	}

	// Declare the incidents exchange
	err = channel.ExchangeDeclare(
		"incidents", // exchange name
		"topic",     // exchange type
		true,        // durable
		false,       // auto-deleted
		false,       // internal
		false,       // no-wait
		nil,         // arguments
	)
	if err != nil {
		channel.Close()
		conn.Close()
		return nil, fmt.Errorf("failed to declare incidents exchange: %w", err)
	}

	// Declare a queue for cluster health summaries
	queue, err := channel.QueueDeclare(
		"incidets_queue_new", // queue name
		true,                       // durable
		false,                      // delete when unused
		false,                      // exclusive
		false,                      // no-wait
		nil,                        // arguments
	)
	if err != nil {
		channel.Close()
		conn.Close()
		return nil, fmt.Errorf("failed to declare queue: %w", err)
	}

	// Bind the queue to the exchange
	err = channel.QueueBind(
		queue.Name,               // queue name
		"incidents.health.summary", // routing key
		"incidents",              // exchange
		false,
		nil,
	)
	if err != nil {
		channel.Close()
		conn.Close()
		return nil, fmt.Errorf("failed to bind queue to exchange: %w", err)
	}

	return &RabbitMQPublisher{
		conn:    conn,
		channel: channel,
	}, nil
}

func (r *RabbitMQPublisher) Publish(ctx context.Context, routingKey string, body string) error {
	if r.channel == nil {
		log.Printf("RabbitMQ not connected, logging message: %s", body)
		return nil
	}

	err := r.channel.Publish(
		"incidents", // exchange
		routingKey,  // routing key
		false,       // mandatory
		false,       // immediate
		amqp.Publishing{
			ContentType: "application/json",
			Body:        []byte(body),
			Timestamp:   time.Now(),
		},
	)
	
	if err != nil {
		log.Printf("Failed to publish to incidents exchange: %v", err)
		return err
	}
	
	log.Printf("Published to incidents exchange with routing key '%s': %s", routingKey, body)
	return nil
}

func (r *RabbitMQPublisher) Close() {
	if r.channel != nil {
		r.channel.Close()
	}
	if r.conn != nil {
		r.conn.Close()
	}
}

// =====================================================================================
// The Main Observer Application
// =====================================================================================

type Observer struct {
	config            *Config
	promCollector     *PrometheusCollector
	lokiCollector     *LokiCollector
	llmSummarizer     *LLMSummarizer
	rabbitmqPublisher *RabbitMQPublisher
	ctx               context.Context
	cancel            context.CancelFunc
}

func NewObserver(config *Config) (*Observer, error) {
	ctx, cancel := context.WithCancel(context.Background())

	publisher, err := NewRabbitMQPublisher(config)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to initialize rabbitmq publisher: %w", err)
	}

	summarizer, err := NewLLMSummarizer(config)
	if err != nil {
		log.Printf("Warning: Failed to initialize LLM summarizer: %v. Continuing without LLM features.", err)
	}

	return &Observer{
		config:            config,
		promCollector:     NewPrometheusCollector(config),
		lokiCollector:     NewLokiCollector(config),
		llmSummarizer:     summarizer,
		rabbitmqPublisher: publisher,
		ctx:               ctx,
		cancel:            cancel,
	}, nil
}

func (o *Observer) Start() {
	log.Println("Observer starting...")
	ticker := time.NewTicker(time.Duration(o.config.AlertInterval) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-o.ctx.Done():
			log.Println("Observation loop stopping.")
			return
		case <-ticker.C:
			if err := o.performObservation(); err != nil {
				log.Printf("Error during observation cycle: %v", err)
			}
		}
	}
}

func (o *Observer) performObservation() error {
	log.Println("--- Starting observation cycle ---")

	// STAGE 1A: Collect aggregate metrics for ALL services
	aggregateMetrics, err := o.promCollector.CollectKeyMetrics(o.ctx)
	if err != nil { return fmt.Errorf("failed to collect aggregate metrics: %w", err) }
	log.Printf("Collected aggregate metrics for %d services", len(aggregateMetrics))
    
    // STAGE 1B: Collect aggregate log stats for ALL services
    logWindow, _ := time.ParseDuration(o.config.LokiLogWindow)
    logStats, err := o.lokiCollector.GetLogStatsByService(o.ctx, int(logWindow.Minutes()))
    if err != nil { log.Printf("Warning: Failed to collect log stats: %v", err) }
    log.Printf("Collected log stats for %d services", len(logStats))

	// STAGE 2: Perform ENHANCED anomaly detection using both metrics and log stats
	servicesOfInterest := o.detectAnomalousServices(aggregateMetrics, logStats)
	if len(servicesOfInterest) == 0 {
		log.Println("No anomalous services detected based on metric and log thresholds.")
	}
	log.Printf("Found %d anomalous services: %v", len(servicesOfInterest), servicesOfInterest)

	significantLogs, err := o.lokiCollector.CollectSignificantLogs(o.ctx, int(logWindow.Minutes()), 200, servicesOfInterest)
	if err != nil { log.Printf("Warning: Failed to collect significant logs: %v", err) }
	log.Printf("Collected %d significant log entries for anomalous services", len(significantLogs))

	focusedData := &ObserverData{
		Cluster:          o.config.ClusterName,
		Timestamp:        time.Now(),
		AggregateMetrics: aggregateMetrics,
		SignificantLogs:  significantLogs,
	}

	// *** NEW: Truncate data to ensure a fixed, small context for the LLM ***
	truncatedData := o.truncateDataForLLM(focusedData)
	
	summary, err := o.llmSummarizer.Summarize(o.ctx, truncatedData)
	if err != nil {
		log.Printf("Error generating LLM summary: %v", err)
	} else {
		err := o.rabbitmqPublisher.Publish(o.ctx, "cluster.health.summary", summary)
		if err != nil { log.Printf("Failed to publish reduced context: %v", err) }
	}

	log.Println("--- Observation cycle completed ---")
	return nil
}

// This function now also needs access to the config for log thresholds
func (o *Observer) detectAnomalousServices(metrics map[string]MetricSnapshot, logStats map[string]LogStats) []string {
	
    // Use a map to avoid adding duplicate service names
    interestMap := make(map[string]string)

	// Infrastructure services to exclude from anomaly detection
	excludedServices := map[string]bool{
		"loki":       true,
		"prometheus": true,
		"promtail":   true,
	}

	// Reason codes for better logging
	const (
		reasonMetric = "MetricThreshold"
		reasonLog    = "LogSeverity"
	)
	
	// --- Check 1: Metric Thresholds ---
	for service, snapshot := range metrics {
		// Skip infrastructure services
		if excludedServices[service] {
			continue
		}
		
		if snapshot.ErrorRate > o.config.ErrorThreshold ||
			snapshot.LatencyP95 > o.config.LatencyThreshold ||
			snapshot.CpuUsageCores*100 > o.config.CPUThreshold {
			
            // We store the reason for flagging this service
			interestMap[service] = reasonMetric
		}
	}

    // --- Check 2: Log Severity and Volume ---
    // Define thresholds for log counts. These should be in your config in a real app.
    const criticalLogThreshold = 1
    const errorLogThreshold = 10
    const warningLogThreshold = 50

    for service, stats := range logStats {
        // Skip infrastructure services
        if excludedServices[service] {
            continue
        }
        
        // If the service is already flagged, we don't need to check it again.
        if _, exists := interestMap[service]; exists {
            continue
        }

        // Any critical/fatal log is an immediate flag.
        if stats.CriticalCount >= criticalLogThreshold {
            interestMap[service] = reasonLog
            continue // Move to the next service
        }

        // A high volume of errors is also a flag.
        if stats.ErrorCount >= errorLogThreshold {
            interestMap[service] = reasonLog
            continue
        }

        // A very high volume of warnings can also indicate a problem.
        if stats.WarningCount >= warningLogThreshold {
            interestMap[service] = reasonLog
        }
    }

	// Convert the map keys to a slice for the return value
	var servicesOfInterest []string
	for service, reason := range interestMap {
		servicesOfInterest = append(servicesOfInterest, service)
        log.Printf("Flagged service '%s' as anomalous. Reason: %s", service, reason)
	}

	return servicesOfInterest
}

// truncateDataForLLM ensures the payload sent to the LLM is small and fixed.
func (o *Observer) truncateDataForLLM(data *ObserverData) *ObserverData {
	truncatedData := &ObserverData{
		Cluster:          data.Cluster,
		Timestamp:        data.Timestamp,
		AggregateMetrics: data.AggregateMetrics,
		SignificantLogs:  []LogEntry{},
	}

	// Limit the number of logs
	numLogs := len(data.SignificantLogs)
	if numLogs > o.config.LLMMaxLogs {
		numLogs = o.config.LLMMaxLogs
	}
	
	// Truncate individual log messages
	for i := 0; i < numLogs; i++ {
		logEntry := data.SignificantLogs[i]
		if len(logEntry.Message) > o.config.LLMMaxLogLength {
			logEntry.Message = logEntry.Message[:o.config.LLMMaxLogLength] + "..."
		}
		truncatedData.SignificantLogs = append(truncatedData.SignificantLogs, logEntry)
	}
    log.Printf("Truncated log data for LLM: %d logs sent, each max %d chars.", len(truncatedData.SignificantLogs), o.config.LLMMaxLogLength)
	return truncatedData
}


func (o *Observer) Stop() {
	log.Println("Observer stopping...")
	o.cancel()
	o.rabbitmqPublisher.Close()
	log.Println("Observer stopped.")
}

func loadConfig() *Config {
	getEnvOrDefault := func(key, defaultValue string) string {
		if value, exists := os.LookupEnv(key); exists { return value }
		return defaultValue
	}
	getEnvOrDefaultInt := func(key string, defaultValue int) int {
		if valueStr, exists := os.LookupEnv(key); exists {
			if value, err := strconv.Atoi(valueStr); err == nil { return value }
		}
		return defaultValue
	}
	getEnvOrDefaultFloat := func(key string, defaultValue float64) float64 {
		if valueStr, exists := os.LookupEnv(key); exists {
			if value, err := strconv.ParseFloat(valueStr, 64); err == nil { return value }
		}
		return defaultValue
	}

	return &Config{
		RabbitMQURL:      getEnvOrDefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
		PrometheusURL:    getEnvOrDefault("PROMETHEUS_URL", "http://localhost:9090"),
		LokiURL:          getEnvOrDefault("LOKI_URL", "http://localhost:3100"),
		LokiLogWindow:    getEnvOrDefault("LOKI_LOG_WINDOW", "10m"),
		GeminiAPIKey:     os.Getenv("GEMINI_API_KEY"),
		ClusterName:      getEnvOrDefault("CLUSTER_NAME", "local-cluster"),
		AlertInterval:    getEnvOrDefaultInt("ALERT_INTERVAL_SECONDS", 60),
		CPUThreshold:     getEnvOrDefaultFloat("CPU_THRESHOLD_PERCENT", 80.0),
		ErrorThreshold:   getEnvOrDefaultFloat("ERROR_THRESHOLD_PERCENT", 5.0),
		LatencyThreshold: getEnvOrDefaultFloat("LATENCY_THRESHOLD_SECONDS", 1.5),
		LLMModelName:     getEnvOrDefault("LLM_MODEL_NAME", "gemini-2.0-flash"),
		LLMMaxLogs:       getEnvOrDefaultInt("LLM_MAX_LOGS", 100),
		LLMMaxLogLength:  getEnvOrDefaultInt("LLM_MAX_LOG_LENGTH", 500),
	}
}

func main() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	log.Println("Initializing KubeMinder Holistic Observer...")

	config := loadConfig()
	observer, err := NewObserver(config)
	if err != nil {
		log.Fatalf("Failed to create observer: %v", err)
	}

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	go observer.Start()

	<-quit
	log.Println("Shutdown signal received.")
	observer.Stop()
	log.Println("Shutdown complete.")
}