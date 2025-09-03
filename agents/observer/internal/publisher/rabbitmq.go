package publisher

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"observer/internal/models"

	"github.com/rabbitmq/amqp091-go"
)

// Publisher handles publishing incidents to RabbitMQ
type Publisher struct {
	conn    *amqp091.Connection
	channel *amqp091.Channel
}

// New creates a new RabbitMQ publisher
func New(url string) (*Publisher, error) {
	conn, err := amqp091.Dial(url)
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

	return &Publisher{
		conn:    conn,
		channel: channel,
	}, nil
}

// PublishIncident publishes an incident to RabbitMQ with routing key "new"
func (p *Publisher) PublishIncident(ctx context.Context, incident *models.Incident) error {
	body, err := json.Marshal(incident)
	if err != nil {
		return fmt.Errorf("failed to marshal incident: %w", err)
	}

	err = p.channel.PublishWithContext(
		ctx,
		"incidents", // exchange
		"new",       // routing key
		false,       // mandatory
		false,       // immediate
		amqp091.Publishing{
			ContentType: "application/json",
			Body:        body,
			Timestamp:   time.Now(),
			MessageId:   incident.ID,
		},
	)

	if err != nil {
		return fmt.Errorf("failed to publish incident: %w", err)
	}

	log.Printf("Published incident %s from %s to RabbitMQ", incident.ID, incident.Source)
	return nil
}

// Close closes the RabbitMQ connection and channel
func (p *Publisher) Close() {
	if p.channel != nil {
		p.channel.Close()
	}
	if p.conn != nil {
		p.conn.Close()
	}
}
