# KubeMinder AI Agents

A distributed AI-powered incident response platform that automates Kubernetes incident detection, analysis, and remediation through specialized microservice agents.

## 🏗️ Architecture Overview

KubeMinder consists of five specialized AI agents that work together to provide intelligent incident response:

- **🔍 Observer**: Ingests data from external sources (Prometheus, Loki) and publishes standardized incident events
- **🧠 Planner**: Analyzes incidents using AI to perform root cause analysis and propose solutions
- **🤝 Collaborator**: Manages user interactions, approvals, and real-time dashboard updates
- **⚡ Actor**: Executes approved remediation plans on infrastructure (Post-MVP)
- **📚 Learner**: Documents resolved incidents and updates the AI knowledge base (Post-MVP)

## 🚀 Quick Start

### Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.9+ (built-in venv module)
- **Go** 1.19+ (for Observer agent)
- **Docker** and Docker Compose
- **Git**

### 1. Clone and Install Root Dependencies
```bash
git clone https://github.com/unichronic/Kbd.git
cd Kbd
npm install
```

### 2. Start Infrastructure
```bash
# Start RabbitMQ message bus
docker-compose up -d rabbitmq
```

Access RabbitMQ Management UI at: http://localhost:15672 (guest/guest)

### 3. Setup Go Agent (Observer)
```bash
cd agents/observer
go mod tidy
cd ../..
```

### 4. Setup Python Agents (with Virtual Environments)

Each Python agent uses **standard Python venv** for virtual environment management:

```bash
# Setup each Python agent
for agent in planner collaborator actor learner; do
    echo "Setting up $agent agent..."
    cd agents/$agent
    python -m venv venv      # Create virtual environment
    source venv/bin/activate # Activate (Linux/macOS)
    # OR on Windows: venv\Scripts\activate
    pip install -r requirements.txt
    pip install -r requirements-test.txt (#only test, not required)
    deactivate
    cd ../..
done
```

#### **Virtual Environment Management:**

- **Each agent has its own isolated virtual environment** in the `venv/` directory
- **To activate an agent's environment:**
  ```bash
  cd agents/planner
  source venv/bin/activate  # Linux/macOS
  # OR on Windows: venv\Scripts\activate
  ```
- **To run commands in the virtual environment:**
  ```bash
  cd agents/planner
  source venv/bin/activate
  python main.py            # Run the agent
  pytest                    # Run tests
  deactivate                # Exit virtual environment
  ```

### 5. Run Development Environment
```bash
# From project root - start all agents
npm run dev

# Or start individual agents
cd agents/planner && npm run dev
cd agents/observer && npm run dev
```

### ⚠️ Important Notes

- **RabbitMQ must be running** before starting any agents
- **All agents will connect to the same RabbitMQ instance** - make sure it's accessible
- **Tests require RabbitMQ** to be running for integration testing
- **Port conflicts**: Each agent uses a different port (8001-8004)

## 🛠️ Development Workflow

### Available Commands

```bash
# Build all agents
npm run build

# Run linting across all agents
npm run lint

# Run tests across all agents
npm run test

# Start development servers
npm run dev
```

### Working with Individual Agents

#### **Python Agents:**
```bash
# Navigate to agent directory
cd agents/planner

# Activate virtual environment
source venv/bin/activate  # Linux/macOS
# OR on Windows: venv\Scripts\activate

# Run the agent
python main.py

# Run tests
pytest

# Exit virtual environment
deactivate
```

#### **Go Agent:**
```bash
# Navigate to agent directory
cd agents/observer

# Run the agent
go run ./cmd/observer

# Run tests
go test ./...

# Build the agent
go build -o dist/observer ./cmd/observer
```

### Agent Ports

- **Observer**: Go service (no HTTP port)
- **Planner**: http://localhost:8001
- **Collaborator**: http://localhost:8002
- **Actor**: http://localhost:8003
- **Learner**: http://localhost:8004

## 📁 Project Structure

```
Kbd/
├── agents/                 # AI agent microservices
│   ├── observer/          # Go-based data ingestion
│   │   ├── cmd/observer/  # Go main application
│   │   ├── go.mod         # Go dependencies
│   │   ├── main_test.go   # Go tests
│   │   └── package.json   # npm scripts
│   ├── planner/           # Python-based incident analysis
│   │   ├── main.py        # FastAPI application
│   │   ├── test_main.py   # Python tests
│   │   ├── requirements.txt # Python dependencies
│   │   ├── requirements-test.txt # Test dependencies
│   │   ├── venv/          # Virtual environment
│   │   └── package.json   # npm scripts
│   ├── collaborator/      # Python-based user interface
│   │   ├── main.py        # FastAPI application
│   │   ├── test_main.py   # Python tests
│   │   ├── requirements.txt # Python dependencies
│   │   ├── requirements-test.txt # Test dependencies
│   │   ├── venv/          # Virtual environment
│   │   └── package.json   # npm scripts
│   ├── actor/             # Python-based remediation (Post-MVP)
│   │   ├── main.py        # FastAPI application
│   │   ├── test_main.py   # Python tests
│   │   ├── requirements.txt # Python dependencies
│   │   ├── requirements-test.txt # Test dependencies
│   │   ├── venv/          # Virtual environment
│   │   └── package.json   # npm scripts
│   └── learner/           # Python-based knowledge management (Post-MVP)
│       ├── main.py        # FastAPI application
│       ├── test_main.py   # Python tests
│       ├── requirements.txt # Python dependencies
│       ├── requirements-test.txt # Test dependencies
│       ├── venv/          # Virtual environment
│       └── package.json   # npm scripts
├── libs/                  # Shared libraries
│   └── event-schemas/     # Event schema definitions
│       └── package.json   # npm scripts
├── docker-compose.yml     # Infrastructure services
├── turbo.json            # Monorepo build configuration
├── package.json          # Root workspace configuration
└── .gitignore            # Git ignore patterns
```

## 🔧 Technology Stack

### Core Technologies
- **Message Bus**: RabbitMQ with AMQP
- **Monorepo**: Turborepo for build orchestration
- **Containerization**: Docker & Docker Compose

### Agent Technologies
- **Observer**: Go, RabbitMQ client (streadway/amqp)
- **Planner**: Python, FastAPI, LangChain, Kimi K2 LLM
- **Collaborator**: Python, FastAPI, WebSocket, PagerDuty/Slack APIs
- **Actor**: Python, FastAPI, Kubernetes client, Cloud SDKs
- **Learner**: Python, FastAPI, ChromaDB, Notion API

## 🧪 Testing

### **Unit Tests:**
```bash
# Run all tests
npm run test

# Run tests for specific agent
cd agents/planner && npm run test
cd agents/observer && npm run test
```

### **Integration Testing:**
```bash
# 1. Start RabbitMQ
docker-compose up -d rabbitmq

# 2. Start all agents
npm run dev

# 3. Monitor the workflow
# - Observer will simulate incidents every 30 seconds
# - Check RabbitMQ Management UI: http://localhost:15672
# - Watch logs to see the complete workflow execution
```

### **Testing the Complete Workflow:**
1. **Start Infrastructure**: `docker-compose up -d rabbitmq`
2. **Start All Agents**: `npm run dev`
3. **Monitor Logs**: Watch each agent process messages
4. **Check RabbitMQ UI**: Verify queues and message flow
5. **Verify End-to-End**: Incident → Plan → Approval → Execution → Resolution

## 🔄 Message Flow & Event Schema

The system uses a complete event-driven workflow with standardized schemas:

### **Message Flow:**
```
Observer → incidents.new → Planner → plans.proposed → Collaborator → plans.approved → Actor → incidents.resolved → Learner
```

### **Event Types:**
- **`incidents.new`**: New incident detected by Observer
- **`incidents.triaged`**: Incident analyzed with AI hypothesis (future)
- **`incidents.resolved`**: Incident successfully resolved by Actor
- **`plans.proposed`**: Remediation plan suggested by Planner
- **`plans.approved`**: Plan approved by Collaborator

### **RabbitMQ Setup:**
Each agent declares its own queues and bindings for resilience:

- **Observer**: Publishes to `incidents` exchange with routing key `new`
- **Planner**: Consumes from `q.incidents.new`, publishes to `plans` exchange with routing key `proposed`
- **Collaborator**: Consumes from `q.plans.proposed`, publishes to `plans` exchange with routing key `approved`
- **Actor**: Consumes from `q.plans.approved`, publishes to `incidents` exchange with routing key `resolved`
- **Learner**: Consumes from `q.incidents.resolved`

### **Event Schemas:**
Standardized JSON schemas are defined in `libs/event-schemas/`:
- **IncidentEvent**: Complete incident lifecycle data
- **PlanEvent**: Remediation plan with execution steps

## 🤝 Contributing

### Development Guidelines

1. **Follow the MVP Roadmap**: Focus on Observer, Planner, and Collaborator first
2. **Use Conventional Commits**: Follow semantic commit message format
3. **Write Tests**: Ensure new features have corresponding tests
4. **Update Documentation**: Keep README and code comments current

### Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run linting and tests: `npm run lint && npm run test`
5. Commit your changes: `git commit -m 'feat: add amazing feature'`
6. Push to your branch: `git push origin feature/amazing-feature`
7. Open a Pull Request

### Code Style

- **Python**: Use `ruff` for linting and formatting
- **Go**: Use `golangci-lint` for linting
- **JavaScript/TypeScript**: Use ESLint and Prettier

## 🚧 MVP Development Roadmap

### Phase 1: Core Infrastructure ✅
- [x] Monorepo setup with Turborepo
- [x] RabbitMQ message bus
- [x] Agent project structure

### Phase 2: Observer Agent (In Progress)
- [ ] Prometheus connector
- [ ] Loki connector
- [ ] Standardized event publishing

### Phase 3: Planner Agent
- [ ] RabbitMQ consumer for new incidents
- [ ] AI-powered root cause analysis
- [ ] LangChain + Kimi K2 integration

### Phase 4: Collaborator Agent
- [ ] REST API for queries
- [ ] WebSocket for real-time updates
- [ ] Dashboard integration

### Phase 5: Post-MVP Features
- [ ] Actor agent for automated remediation
- [ ] Learner agent for knowledge management
- [ ] Advanced integrations (GitHub, Notion, PagerDuty, Slack)

## 🔐 Environment Variables

Create `.env` files in agent directories as needed:

```bash
# Example for Planner agent
KIMI_API_KEY=your_kimi_api_key
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
LOKI_URL=http://localhost:3100
```

## 📚 Additional Resources

- [Project Documentation](./project.md) - Detailed development plan
- [RabbitMQ Management UI](http://localhost:15672) - Message queue monitoring
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - Python API framework
- [LangChain Documentation](https://python.langchain.com/) - AI framework

## 📄 License

This project is licensed under the ISC License - see the [LICENSE](LICENSE) file for details.

## 🔧 Troubleshooting

### Common Issues

#### **"Failed to connect to RabbitMQ"**
- Ensure RabbitMQ is running: `docker-compose up -d rabbitmq`
- Check if port 5672 is available: `docker ps`
- Verify RabbitMQ logs: `docker-compose logs rabbitmq`

#### **"Module not found" errors in Python agents**
- Ensure you're in the correct agent directory
- Create virtual environment: `python -m venv venv`
- Activate virtual environment: `source venv/bin/activate` (Linux/macOS) or `venv\Scripts\activate` (Windows)
- Install dependencies: `pip install -r requirements.txt`

#### **"Go module not found" errors**
- Run `go mod tidy` in the `agents/observer` directory
- Ensure Go 1.19+ is installed: `go version`

#### **Port conflicts**
- Each agent uses a different port (8001-8004)
- Check if ports are in use: `netstat -tulpn | grep :800`
- Stop conflicting services or change ports in agent configs

#### **Tests failing**
- Ensure RabbitMQ is running before running tests
- Activate virtual environment and run tests: `cd agents/planner && source venv/bin/activate && pytest`
- Check agent logs for connection issues

### Getting Help

- **Check logs**: Each agent logs to stdout with detailed error messages
- **RabbitMQ Management UI**: http://localhost:15672 (guest/guest)
- **Agent Health Checks**: 
  - Planner: http://localhost:8001/health
  - Collaborator: http://localhost:8002/health
  - Actor: http://localhost:8003/health
  - Learner: http://localhost:8004/health

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/unichronic/Kbd/issues)
- **Discussions**: [GitHub Discussions](https://github.com/unichronic/Kbd/discussions)

---

**Built with ❤️ for the Kubernetes community**