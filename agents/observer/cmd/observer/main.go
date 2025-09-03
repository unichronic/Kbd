package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"observer/internal/config"
	"observer/internal/handlers"
	"observer/internal/publisher"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	log.Println("Starting Observer Agent...")

	// Load configuration
	cfg := config.Load()
	log.Printf("Configuration loaded: RabbitMQ=%s, Port=%s", cfg.RabbitMQURL, cfg.ServerPort)

	// Initialize RabbitMQ publisher
	pub, err := publisher.New(cfg.RabbitMQURL)
		if err != nil {
		log.Fatalf("Failed to initialize RabbitMQ publisher: %v", err)
	}
	defer pub.Close()

	// Initialize handlers
	promHandler := handlers.NewPrometheusHandler(pub)
	pagerDutyHandler := handlers.NewPagerDutyHandler(pub)

	// Setup HTTP routes
	http.HandleFunc("/webhook/prometheus", promHandler.HandleWebhook)
	http.HandleFunc("/webhook/pagerduty", pagerDutyHandler.HandleWebhook)
	http.HandleFunc("/health", healthHandler)

	// Create HTTP server
	server := &http.Server{
		Addr:         ":" + cfg.ServerPort,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Start server in goroutine
	go func() {
		log.Printf("Observer Agent listening on port %s", cfg.ServerPort)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down Observer Agent...")

	// Graceful shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Printf("Server forced to shutdown: %v", err)
	}

	log.Println("Observer Agent stopped")
}

// healthHandler provides a simple health check endpoint
func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}
