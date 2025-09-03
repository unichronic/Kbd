package main

import (
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/google/uuid"
	amqp "github.com/rabbitmq/amqp091-go"
)

type Incident struct {
	ID              string `json:"id"`
	Timestamp       string `json:"timestamp"`
	Status          string `json:"status"`
	Severity        string `json:"severity"`
	Source          string `json:"source"`
	Title           string `json:"title"`
	Description     string `json:"description"`
	AffectedService string `json:"affected_service"`
}

func main() {
	log.Println("Observer starting...")

	// Connect to RabbitMQ
	conn, err := amqp.Dial("amqp://guest:guest@localhost:5672/")
	if err != nil {
		log.Fatalf("Failed to connect to RabbitMQ: %v", err)
	}
	defer conn.Close()

	ch, err := conn.Channel()
	if err != nil {
		log.Fatalf("Failed to open channel: %v", err)
	}
	defer ch.Close()

	// Declare exchange
	err = ch.ExchangeDeclare("incidents", "topic", true, false, false, false, nil)
	if err != nil {
		log.Fatalf("Failed to declare exchange: %v", err)
	}

	log.Println("Observer: Exchange declared")

	// Simulate incidents every 30 seconds
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				incident := Incident{
					ID:              uuid.New().String(),
					Timestamp:       time.Now().Format(time.RFC3339),
					Status:          "new",
					Severity:        "high",
					Source:          "prometheus",
					Title:           "High CPU Usage Alert",
					Description:     "CPU usage exceeded 80%",
					AffectedService: "web-app",
				}

				body, _ := json.Marshal(incident)

				err := ch.Publish("incidents", "new", false, false, amqp.Publishing{
					ContentType: "application/json",
					Body:        body,
				})

				if err != nil {
					log.Printf("Failed to publish: %v", err)
				} else {
					log.Printf("Published incident: %s", incident.ID)
				}
			}
		}
	}()

	// Wait for interrupt
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Observer shutting down...")
}
