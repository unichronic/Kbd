# Learner Agent

The Learner Agent is the long-term memory system for KubeMinder AI. It processes resolved incidents to create an evolving knowledge base that improves future incident diagnosis and resolution.

## Overview

The Learner Agent implements an "evolving memory" system that:

1. **Consumes** resolved incidents from RabbitMQ queue `q.incidents.resolved`
2. **Documents** incidents as structured post-mortems in Notion
3. **Memorizes** incidents as vector embeddings in ChromaDB for similarity matching

This memory system enables the Planner Agent to find similar past incidents, improving its diagnostic accuracy over time.

## Architecture

### Components

- **RabbitMQ Consumer (pika)**: Listens for resolved incidents
- **Vectorization Engine (sentence-transformers)**: Converts text summaries to embeddings
- **Vector Database (ChromaDB)**: Stores embeddings for similarity search
- **Notion Client (notion-client)**: Creates post-mortem documentation
- **FastAPI Server**: Provides health checks and search endpoints

### Data Flow

```
Resolved Incident → RabbitMQ → Learner Agent → [Notion + ChromaDB]
```

## Setup

### Prerequisites

1. **Docker & Docker Compose**: For running ChromaDB and RabbitMQ
2. **Python 3.8+**: For running the agent
3. **Notion API Key** (optional): For post-mortem documentation

### Installation

1. **Start Dependencies**:
   ```bash
   docker-compose up -d
   ```

2. **Install Python Dependencies**:
   ```bash
   cd agents/learner
   pip install -r requirements.txt
   ```

3. **Set Environment Variables** (optional):
   ```bash
   export NOTION_API_KEY="your_notion_api_key"
   export NOTION_DATABASE_ID="your_database_id"
   ```

### Running the Agent

```bash
cd agents/learner
python main.py
```

The agent will:
- Start on port 8004
- Connect to ChromaDB on localhost:8000
- Connect to RabbitMQ on localhost:5672
- Begin consuming from `q.incidents.resolved` queue

## API Endpoints

### Health Check
```bash
GET /health
```
Returns the status of all components.

### Statistics
```bash
GET /stats
```
Returns the total number of incidents stored in ChromaDB.

### Search
```bash
GET /search/{query}?limit=5
```
Searches for similar incidents using vector similarity.

Example:
```bash
curl "http://localhost:8004/search/high%20cpu%20usage?limit=3"
```

## Testing

### Automated Testing

Run the test script to verify the complete workflow:

```bash
cd agents/learner
python test_learner.py
```

This will:
1. Test API endpoints
2. Publish sample incidents to RabbitMQ
3. Verify processing and storage

### Manual Testing

1. **Publish Test Incident**:
   ```bash
   # Use RabbitMQ Management UI at http://localhost:15672
   # Go to Exchanges → incidents → Publish message
   # Routing key: resolved
   # Payload: (paste content from sample_incident.json)
   ```

2. **Verify Processing**:
   - Check agent logs for processing messages
   - Verify ChromaDB storage via API
   - Check Notion database (if configured)

### Sample Data

- `sample_incident.json`: Single test incident
- `sample_incidents.json`: Multiple test incidents
- `test_learner.py`: Automated test script

## Configuration

### ChromaDB

ChromaDB runs in Docker and is automatically configured. The agent connects to:
- Host: localhost
- Port: 8000
- Collection: "incidents"

### Notion Integration

To enable Notion post-mortems:

1. Create a Notion integration and get API key
2. Create a database in Notion
3. Set environment variables:
   ```bash
   export NOTION_API_KEY="secret_..."
   export NOTION_DATABASE_ID="database_id"
   ```

The database should have these properties:
- Name (title)
- Incident ID (rich_text)
- Severity (select)
- Service (rich_text)

### RabbitMQ

The agent connects to RabbitMQ with these settings:
- Host: localhost
- Port: 5672
- Exchange: incidents (topic)
- Queue: q.incidents.resolved
- Routing Key: resolved

## Incident Data Format

The agent expects resolved incidents in this format:

```json
{
  "id": "INC-2025-01-03-001",
  "timestamp": "2025-01-03T10:30:00Z",
  "status": "resolved",
  "severity": "high",
  "source": "prometheus",
  "title": "High CPU Usage on Auth Service",
  "description": "Detailed incident description...",
  "affected_service": "auth-service",
  "affected_namespace": "production",
  "ai_hypothesis": "Root cause analysis...",
  "confidence_score": 0.87,
  "resolution_action": "Action taken to resolve...",
  "resolution_notes": "Additional resolution details..."
}
```

## Troubleshooting

### Common Issues

1. **ChromaDB Connection Failed**:
   - Ensure ChromaDB is running: `docker-compose ps`
   - Check port 8000 is available

2. **RabbitMQ Connection Failed**:
   - Ensure RabbitMQ is running: `docker-compose ps`
   - Check port 5672 is available

3. **Notion Integration Not Working**:
   - Verify API key and database ID
   - Check database permissions
   - Agent will continue without Notion (optional feature)

4. **Embedding Model Download**:
   - First run downloads the model (~90MB)
   - Ensure internet connection for initial setup

### Logs

The agent provides detailed logging:
- ✓ Success indicators
- ✗ Error indicators
- ⚠ Warning indicators
- 📚 Processing indicators

### Performance

- **Model Loading**: ~2-3 seconds on first run
- **Embedding Generation**: ~100ms per incident
- **ChromaDB Storage**: ~50ms per incident
- **Memory Usage**: ~200MB (including model)

## Development

### Adding New Features

1. **New Vector Search**: Modify the search endpoint
2. **Additional Metadata**: Update the memorize_incident function
3. **Custom Summaries**: Modify create_incident_summary function
4. **New Integrations**: Add new clients alongside Notion

### Testing Changes

1. Run unit tests: `python -m pytest test_main.py`
2. Run integration tests: `python test_learner.py`
3. Test with real data via RabbitMQ

## Integration with Other Agents

The Learner Agent integrates with:

- **Planner Agent**: Queries ChromaDB for similar incidents
- **Actor Agent**: Sends resolved incidents to RabbitMQ
- **Observer Agent**: Provides incident data for processing

The evolving memory system improves the entire platform's diagnostic capabilities over time.
