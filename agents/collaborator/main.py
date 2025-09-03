import json
import pika
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import uvicorn
import asyncio
from typing import Dict, Any, List

app = FastAPI(title="Collaborator Agent")

# Pydantic models for API requests/responses
class QueryRequest(BaseModel):
    query: str
    context: Dict[str, Any] = {}

class QueryResponse(BaseModel):
    response: str
    confidence: float
    sources: List[str] = []
    status: str = "success"

class IncidentUpdate(BaseModel):
    type: str
    data: Dict[str, Any]

# Simple RabbitMQ setup
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Declare exchange and queue
channel.exchange_declare(exchange='plans', exchange_type='topic', durable=True)
channel.queue_declare(queue='q.plans.proposed', durable=True)
channel.queue_bind(exchange='plans', queue='q.plans.proposed', routing_key='proposed')

def process_plan(ch, method, properties, body):
    """Approve plan and publish it"""
    plan = json.loads(body)
    print(f"Processing plan: {plan['id']}")
    
    # Auto-approve medium risk plans
    if plan.get("risk_level") == "medium":
        plan["status"] = "approved"
        plan["approved_by"] = "auto_approval"
        
        # Publish approved plan
        channel.basic_publish(
            exchange='plans',
            routing_key='approved',
            body=json.dumps(plan)
        )
        
        print(f"Approved plan: {plan['id']}")
    else:
        print(f"Plan {plan['id']} requires manual approval")
    
    ch.basic_ack(delivery_tag=method.delivery_tag)

# Start consuming
channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='q.plans.proposed', on_message_callback=process_plan)

@app.get("/")
def root():
    return {"message": "Collaborator Agent is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/api/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """Handle natural language queries from frontend"""
    try:
        # Mock implementation - replace with actual AI logic
        query_lower = request.query.lower()
        
        if "status" in query_lower or "health" in query_lower:
            response = "System is currently operational. All agents are running normally."
            confidence = 0.9
            sources = ["system_health", "agent_status"]
        elif "incident" in query_lower:
            response = "No active incidents detected. Last incident was resolved 2 hours ago."
            confidence = 0.85
            sources = ["incident_database", "monitoring_system"]
        elif "metrics" in query_lower or "performance" in query_lower:
            response = "Current system metrics: CPU usage at 45%, Memory at 62%, Network latency normal."
            confidence = 0.8
            sources = ["prometheus", "grafana"]
        else:
            response = f"Processing query: {request.query}. This is a mock response - implement actual AI logic here."
            confidence = 0.7
            sources = ["general_knowledge"]
        
        return QueryResponse(
            response=response,
            confidence=confidence,
            sources=sources,
            status="success"
        )
    except Exception as e:
        return QueryResponse(
            response=f"Error processing query: {str(e)}",
            confidence=0.0,
            sources=[],
            status="error"
        )

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await websocket.accept()
    try:
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({
            "type": "connection",
            "data": {"message": "Connected to Collaborator Agent", "timestamp": asyncio.get_event_loop().time()}
        }))
        
        # Keep connection alive and send periodic updates
        while True:
            # In a real implementation, this would listen to RabbitMQ events
            # For now, we'll send a heartbeat every 30 seconds
            await asyncio.sleep(30)
            
            heartbeat = {
                "type": "heartbeat",
                "data": {
                    "message": "System heartbeat",
                    "timestamp": asyncio.get_event_loop().time(),
                    "agents_status": "all_healthy"
                }
            }
            
            await websocket.send_text(json.dumps(heartbeat))
            
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close()

@app.get("/api/incidents/recent")
async def get_recent_incidents():
    """Get recent incidents (mock data for now)"""
    return {
        "incidents": [
            {
                "id": "INC-1024",
                "title": "Spike in 5xx responses on api-gateway",
                "severity": "critical",
                "status": "active",
                "hypothesis": "Possible upstream timeout in user-service",
                "occurredAt": "2m ago",
                "service": "api-gateway"
            },
            {
                "id": "INC-1023", 
                "title": "Elevated pod restarts in kube-system",
                "severity": "warning",
                "status": "acknowledged",
                "hypothesis": "Node drain during autoscaling event",
                "occurredAt": "14m ago",
                "service": "kubelet"
            }
        ],
        "status": "success"
    }

if __name__ == "__main__":
    print("Collaborator: Starting to consume plans...")
    # Start consuming in background
    import threading
    threading.Thread(target=channel.start_consuming, daemon=True).start()
    
    # Start FastAPI
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
