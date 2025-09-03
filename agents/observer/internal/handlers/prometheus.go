package handlers

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"observer/internal/models"
	"observer/internal/publisher"

	"github.com/google/uuid"
)

// PrometheusHandler handles webhook requests from Prometheus Alertmanager
type PrometheusHandler struct {
	publisher *publisher.Publisher
}

// NewPrometheusHandler creates a new Prometheus webhook handler
func NewPrometheusHandler(pub *publisher.Publisher) *PrometheusHandler {
	return &PrometheusHandler{
		publisher: pub,
	}
}

// HandleWebhook processes incoming Prometheus Alertmanager webhooks
func (h *PrometheusHandler) HandleWebhook(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var payload models.PrometheusPayload
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		log.Printf("Failed to decode Prometheus payload: %v", err)
		http.Error(w, "Invalid JSON payload", http.StatusBadRequest)
		return
	}

	log.Printf("Received %d alert(s) from Prometheus", len(payload.Alerts))

	for _, alert := range payload.Alerts {
		incident := h.standardizeAlert(alert)
		if err := h.publisher.PublishIncident(r.Context(), &incident); err != nil {
			log.Printf("Failed to publish incident: %v", err)
			// Continue processing other alerts even if one fails
		}
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

// standardizeAlert converts a Prometheus alert to our standardized Incident format
func (h *PrometheusHandler) standardizeAlert(alert models.PrometheusAlert) models.Incident {
	return models.Incident{
		ID:        "INC-" + uuid.New().String(),
		Service:   alert.Labels["service"],
		Title:     alert.Annotations["summary"],
		Summary:   alert.Annotations["description"],
		Severity:  alert.Labels["severity"],
		Timestamp: time.Now().UTC(),
		Source:    "prometheus",
		RawAlert:  alert,
	}
}
