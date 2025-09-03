import json
import pika
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Planner Agent")

# Simple RabbitMQ setup
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Declare exchanges and queue
channel.exchange_declare(exchange='incidents', exchange_type='topic', durable=True)
channel.exchange_declare(exchange='plans', exchange_type='topic', durable=True)
channel.queue_declare(queue='q.incidents.new', durable=True)
channel.queue_bind(exchange='incidents', queue='q.incidents.new', routing_key='new')

def process_incident(ch, method, properties, body):
    """Process incident and create plan"""
    incident = json.loads(body)
    print(f"Processing incident: {incident['id']}")
    
    # Simple plan creation
    plan = {
        "id": f"plan_{incident['id']}",
        "incident_id": incident["id"],
        "status": "proposed",
        "risk_level": "medium",
        "title": f"Fix {incident.get('title', 'Incident')}",
        "steps": [{"action": "scale_up", "service": incident.get("affected_service", "web-app")}]
    }
    
    # Publish plan
    channel.basic_publish(
        exchange='plans',
        routing_key='proposed',
        body=json.dumps(plan)
    )
    
    print(f"Published plan: {plan['id']}")
    ch.basic_ack(delivery_tag=method.delivery_tag)

# Start consuming
channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='q.incidents.new', on_message_callback=process_incident)

@app.get("/")
def root():
    return {"message": "Planner Agent is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    print("Planner: Starting to consume incidents...")
    # Start consuming in background
    import threading
    threading.Thread(target=channel.start_consuming, daemon=True).start()
    
    # Start FastAPI
    uvicorn.run(app, host="0.0.0.0", port=8001)
