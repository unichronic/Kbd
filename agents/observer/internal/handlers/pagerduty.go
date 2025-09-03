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

// PagerDutyHandler handles webhook requests from PagerDuty
type PagerDutyHandler struct {
	publisher *publisher.Publisher
}

// NewPagerDutyHandler creates a new PagerDuty webhook handler
func NewPagerDutyHandler(pub *publisher.Publisher) *PagerDutyHandler {
	return &PagerDutyHandler{
		publisher: pub,
	}
}

// HandleWebhook processes incoming PagerDuty webhooks
func (h *PagerDutyHandler) HandleWebhook(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var payload models.PagerDutyPayload
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		log.Printf("Failed to decode PagerDuty payload: %v", err)
		http.Error(w, "Invalid JSON payload", http.StatusBadRequest)
		return
	}

	log.Printf("Received %d message(s) from PagerDuty", len(payload.Messages))

	for _, msg := range payload.Messages {
		// Only process incident triggers
		if msg.Event == "incident.trigger" {
			incident := h.standardizeAlert(msg)
			if err := h.publisher.PublishIncident(r.Context(), &incident); err != nil {
				log.Printf("Failed to publish incident: %v", err)
				// Continue processing other messages even if one fails
			}
		}
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

// standardizeAlert converts a PagerDuty message to our standardized Incident format
func (h *PagerDutyHandler) standardizeAlert(message models.PagerDutyMessage) models.Incident {
	return models.Incident{
		ID:        "INC-" + uuid.New().String(),
		Service:   message.Incident.Service.Name,
		Title:     message.Incident.Title,
		Summary:   message.Incident.Summary,
		Severity:  message.Incident.Urgency, // PagerDuty uses "urgency"
		Timestamp: time.Now().UTC(),
		Source:    "pagerduty",
		RawAlert:  message,
	}
}
