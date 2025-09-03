import json, time
import pika

RABBIT_URL = "amqp://guest:guest@localhost:5672/"

params = pika.URLParameters(RABBIT_URL)
conn = pika.BlockingConnection(params)
ch = conn.channel()

# Ensure exchanges exist
ch.exchange_declare(exchange="incidents", exchange_type="topic", durable=True)
ch.exchange_declare(exchange="plans", exchange_type="topic", durable=True)

# Publish a test incident
incident = {
  "id": "inc-verify-010",
  "title": "E2E verification high error rate",
  "affected_service": "payments-api",
  "symptoms": ["5xx spike", "latency p95 degraded"],
  "metrics": {"error_rate": 0.2, "latency_p95_ms": 900},
  "logs": ["ERR timeout", "DB conn reset"],
  "hypothesis": "DB connection pool exhaustion"
}
ch.basic_publish(exchange="incidents", routing_key="new", body=json.dumps(incident))

# Temp queue bound to plans.proposed
q = ch.queue_declare(queue="", exclusive=True)
qname = q.method.queue
ch.queue_bind(exchange="plans", queue=qname, routing_key="proposed")

# Poll for a published plan
plan = None
for _ in range(60):
    m, props, body = ch.basic_get(queue=qname, auto_ack=True)
    if body:
        plan = json.loads(body)
        break
    time.sleep(0.5)

print(json.dumps({"received_plan": plan is not None, "plan": plan}, indent=2))
conn.close()
