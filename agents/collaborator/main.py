import json
import pika
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Collaborator Agent")

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

if __name__ == "__main__":
    print("Collaborator: Starting to consume plans...")
    # Start consuming in background
    import threading
    threading.Thread(target=channel.start_consuming, daemon=True).start()
    
    # Start FastAPI
    uvicorn.run(app, host="0.0.0.0", port=8002)
