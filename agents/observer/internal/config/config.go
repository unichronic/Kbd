package config

import (
	"os"
	"strconv"
)

// Config holds all configuration for the Observer Agent
type Config struct {
	RabbitMQURL string
	ServerPort  string
	LogLevel    string
	MaxRetries  int
	RetryDelay  int
}

// Load reads configuration from environment variables with sensible defaults
func Load() *Config {
	return &Config{
		RabbitMQURL: getEnvOrDefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
		ServerPort:  getEnvOrDefault("SERVER_PORT", "8080"),
		LogLevel:    getEnvOrDefault("LOG_LEVEL", "info"),
		MaxRetries:  getEnvOrDefaultInt("MAX_RETRIES", 3),
		RetryDelay:  getEnvOrDefaultInt("RETRY_DELAY_MS", 1000),
	}
}

// getEnvOrDefault returns the environment variable value or the default if not set
func getEnvOrDefault(key, defaultValue string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultValue
}

// getEnvOrDefaultInt returns the environment variable value as int or the default if not set
func getEnvOrDefaultInt(key string, defaultValue int) int {
	if valueStr, exists := os.LookupEnv(key); exists {
		if value, err := strconv.Atoi(valueStr); err == nil {
			return value
		}
	}
	return defaultValue
}
