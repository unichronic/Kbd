import json
import pika
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Actor Agent")

# Simple RabbitMQ setup
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Declare exchanges and queue
channel.exchange_declare(exchange='plans', exchange_type='topic', durable=True)
channel.exchange_declare(exchange='incidents', exchange_type='topic', durable=True)
channel.queue_declare(queue='q.plans.approved', durable=True)
channel.queue_bind(exchange='plans', queue='q.plans.approved', routing_key='approved')

def process_plan(ch, method, properties, body):
    """Execute plan and publish resolution"""
    plan = json.loads(body)
    print(f"Executing plan: {plan['id']}")
    
    # Mock execution
    print(f"Executing steps: {plan.get('steps', [])}")
    
    # Publish resolution
    resolution = {
        "id": plan["incident_id"],
        "status": "resolved",
        "resolution_action": f"Executed plan: {plan['id']}",
        "plan_id": plan["id"]
    }
    
    channel.basic_publish(
        exchange='incidents',
        routing_key='resolved',
        body=json.dumps(resolution)
    )
    
    print(f"Published resolution for incident: {plan['incident_id']}")
    ch.basic_ack(delivery_tag=method.delivery_tag)

# Start consuming
channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='q.plans.approved', on_message_callback=process_plan)

@app.get("/")
def root():
    return {"message": "Actor Agent is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    print("Actor: Starting to consume approved plans...")
    # Start consuming in background
    import threading
    threading.Thread(target=channel.start_consuming, daemon=True).start()
    
    # Start FastAPI
    uvicorn.run(app, host="0.0.0.0", port=8003)
