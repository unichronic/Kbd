from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
import requests
import httpx
import asyncio
from typing import List, Dict, Any
from pydantic import BaseModel
import sys
from pymongo import MongoClient
from bson import ObjectId

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'agents', 'architect'))

# Try to import architect functions, fallback if not available
try:
    from architect_core import generate_clarifying_questions, generate_infra_plan
    ARCHITECT_AVAILABLE = True
except ImportError as e:
    print(f"[!] Warning: Could not import architect_core: {e}")
    ARCHITECT_AVAILABLE = False

# MongoDB setup
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["incident_db"]
collection = db["plans"]

# Helper to convert ObjectId to string
class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)

# Request models
class InfraRequest(BaseModel):
    prompt: str

class InfraAnswers(BaseModel):
    original_prompt: str
    answers: List[str]

class DeployRequest(BaseModel):
    infrastructure_code: str

app = FastAPI(
    title="KubeMinder API Gateway",
    description="Unified API gateway for all KubeMinder agents",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:8080",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent endpoints mapping
AGENT_ENDPOINTS = {
    "planner": "http://localhost:8001",
    "collaborator": "http://localhost:8002", 
    "actor": "http://localhost:8003",
    "learner": "http://localhost:8004"
}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "KubeMinder API Gateway",
        "version": "1.0.0",
        "agents": list(AGENT_ENDPOINTS.keys())
    }

@app.get("/api/health")
async def health_check():
    """Check health of all agents"""
    health_status = {}
    async with httpx.AsyncClient() as client:
        for agent, url in AGENT_ENDPOINTS.items():
            try:
                response = await client.get(f"{url}/health", timeout=5.0)
                health_status[agent] = {
                    "status": "healthy",
                    "response": response.json()
                }
            except Exception as e:
                health_status[agent] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
    return {
        "gateway": "healthy",
        "agents": health_status,
        "timestamp": asyncio.get_event_loop().time()
    }

@app.get("/api/incidents")
async def get_incidents():
    """Get incidents from MongoDB"""
    try:
        incidents = list(collection.find({}))
        # Convert ObjectId to string for JSON serialization
        for incident in incidents:
            if '_id' in incident:
                incident['_id'] = str(incident['_id'])
        return {
            "incidents": incidents,
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch incidents: {str(e)}")

@app.post("/api/query")
async def submit_query(query: Dict[str, Any]):
    """Submit natural language query to collaborator"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_ENDPOINTS['collaborator']}/api/query",
                json=query,
                timeout=30.0
            )
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.get("/api/stats")
async def get_stats():
    """Get learner agent statistics"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AGENT_ENDPOINTS['learner']}/stats")
            return response.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error forwarding request to architect: {e}")

@app.post("/api/infrastructure/deploy")
async def deploy_infrastructure(request: DeployRequest):
    """Forwards a request to the Actor agent to create a deployment package."""
    actor_url = "http://localhost:8003/api/package/create"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(actor_url, json={"infrastructure_code": request.infrastructure_code})
            response.raise_for_status()  # Raise an exception for bad status codes
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Error from actor agent: {e.response.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error forwarding request to actor: {e}")

@app.get("/api/agents")
async def get_agents():
    """Get information about all agents"""
    return {
        "agents": [
            {
                "name": "planner",
                "url": AGENT_ENDPOINTS["planner"],
                "description": "Analyzes incidents and creates remediation plans"
            },
            {
                "name": "collaborator", 
                "url": AGENT_ENDPOINTS["collaborator"],
                "description": "Handles user interactions and approvals"
            },
            {
                "name": "actor",
                "url": AGENT_ENDPOINTS["actor"],
                "description": "Executes approved remediation plans"
            },
            {
                "name": "learner",
                "url": AGENT_ENDPOINTS["learner"],
                "description": "Documents incidents and updates knowledge base"
            }
        ]
    }

@app.post("/api/infrastructure/questions")
async def generate_questions(request: InfraRequest):
    """Generate clarifying questions for infrastructure setup"""
    if not ARCHITECT_AVAILABLE:
        # Fallback questions when Gemini is not available
        return {
            "status": "success",
            "source": "fallback",
            "questions": [
                "What cloud provider do you prefer (AWS, GCP, Azure)?",
                "Do you need a database? If yes, which type (PostgreSQL, MySQL, MongoDB)?",
                "Do you need auto-scaling and load balancing?",
                "What CI/CD platform do you prefer (GitHub Actions, Jenkins, GitLab CI)?"
            ],
            "original_prompt": request.prompt
        }
    
    try:
        questions = generate_clarifying_questions(request.prompt)
        return {
            "status": "success",
            "source": "gemini",
            "questions": questions,
            "original_prompt": request.prompt
        }
    except Exception as e:
        print(f"[!] Error generating questions: {e}")
        # Fallback questions on error
        return {
            "status": "success",
            "source": "fallback",
            "questions": [
                "What cloud provider do you prefer (AWS, GCP, Azure)?",
                "Do you need a database? If yes, which type (PostgreSQL, MySQL, MongoDB)?",
                "Do you need auto-scaling and load balancing?",
                "What CI/CD platform do you prefer (GitHub Actions, Jenkins, GitLab CI)?"
            ],
            "original_prompt": request.prompt
        }

@app.post("/api/infrastructure/generate")
async def generate_infrastructure(request: InfraAnswers):
    """Generate complete infrastructure setup from answers"""
    if not ARCHITECT_AVAILABLE:
        # Fallback infrastructure template
        return {
            "status": "success",
            "source": "fallback",
            "infrastructure": f"""## Dockerfile
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

## terraform/main.tf
```hcl
variable "environment" {{
  description = "Environment name"
  type        = string
  default     = "staging"
}}

resource "aws_instance" "web" {{
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
  
  tags = {{
    Name        = "${{var.environment}}-web-server"
    Environment = var.environment
  }}
}}

output "instance_ip" {{
  value = aws_instance.web.public_ip
}}
```

## docker-compose.yml
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=staging
  
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
""",
            "original_prompt": request.original_prompt,
            "answers": request.answers
        }
    
    try:
        infra_plan = generate_infra_plan(request.original_prompt, request.answers)
        return {
            "status": "success",
            "source": "gemini",
            "infrastructure": infra_plan,
            "original_prompt": request.original_prompt,
            "answers": request.answers
        }
    except Exception as e:
        print(f"[!] Error generating infrastructure: {e}")
        # Return fallback template on error
        return {
            "status": "success", 
            "source": "fallback",
            "infrastructure": f"""## Dockerfile
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

## Error
Failed to generate infrastructure with Gemini. Please check:
1. GEMINI_API_KEY is set correctly
2. Network connectivity is available
3. Gemini API quota is not exceeded

Error: {str(e)}""",
            "original_prompt": request.original_prompt,
            "answers": request.answers
        }

if __name__ == "__main__":
    print("🚀 Starting KubeMinder API Gateway on port 8005...")
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)
