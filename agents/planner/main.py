import json
import os
import threading
from typing import Any, Dict, List

import pika
from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

try:
    import google.generativeai as genai
except Exception:  # Library may not be installed yet during import-time in some environments
    genai = None  # type: ignore


app = FastAPI(title="Planner Agent")


# Configuration and setup
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


def create_rabbitmq_channel(url: str) -> pika.adapters.blocking_connection.BlockingChannel:
    parameters = pika.URLParameters(url)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    # Declare exchanges and queues (idempotent)
    channel.exchange_declare(exchange="incidents", exchange_type="topic", durable=True)
    channel.exchange_declare(exchange="plans", exchange_type="topic", durable=True)
    channel.queue_declare(queue="q.incidents.new", durable=True)
    channel.queue_bind(exchange="incidents", queue="q.incidents.new", routing_key="new")

    return channel


def ensure_gemini_client():
    if GEMINI_API_KEY is None:
        raise RuntimeError("GEMINI_API_KEY is not set in environment")
    if genai is None:
        raise RuntimeError("google-generativeai is not installed. Please install dependencies.")
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(GEMINI_MODEL)


def build_planner_prompt(incident: Dict[str, Any]) -> str:
    title = incident.get("title", "Unknown Incident")
    service = incident.get("affected_service", "unknown-service")
    hypothesis = incident.get("hypothesis", "")
    symptoms = incident.get("symptoms", [])
    metrics = incident.get("metrics", {})
    logs = incident.get("logs", [])

    return (
        "You are an SRE Planner agent for a Kubernetes platform. "
        "Given an incident, produce a concrete remediation plan in structured JSON with fields: "
        "id, incident_id, status, risk_level, title, summary, rationale, steps (array of objects with fields: action, target, cmd, notes), "
        "rollout (canary/bluegreen), and verification (list of checks). Avoid markdown."
        f"\n\nIncident Title: {title}"
        f"\nAffected Service: {service}"
        f"\nHypothesis: {hypothesis}"
        f"\nSymptoms: {symptoms}"
        f"\nKey Metrics: {metrics}"
        f"\nRecent Logs (truncated): {logs[:5]}"
        "\n\nConstraints:"
        "\n- Prefer safe, reversible actions."
        "\n- Include pre-checks and post-verification."
        "\n- Include rollback guidance if needed."
        "\n- Provide short shell commands when appropriate."
    )


def generate_plan_with_gemini(incident: Dict[str, Any]) -> Dict[str, Any]:
    model = ensure_gemini_client()
    prompt = build_planner_prompt(incident)
    response = model.generate_content(prompt)
    text = response.text if hasattr(response, "text") else str(response)

    # Try parsing JSON from the model; if it fails, fallback to simple plan
    plan: Dict[str, Any]
    try:
        plan = json.loads(text)
    except Exception:
        plan = {
            "id": f"plan_{incident.get('id', 'unknown')}",
            "incident_id": incident.get("id", "unknown"),
            "status": "proposed",
            "risk_level": "medium",
            "title": f"Remediate {incident.get('title', 'Incident')}",
            "summary": "Auto-generated fallback plan.",
            "rationale": "Model output was unstructured; using safe default actions.",
            "steps": [
                {
                    "action": "increase_replicas",
                    "target": incident.get("affected_service", "web-app"),
                    "cmd": "kubectl scale deploy/<service> --replicas=+1",
                    "notes": "Scale cautiously while monitoring error rates and latency."
                }
            ],
            "rollout": "canary",
            "verification": [
                "Check error rate < 1%",
                "Latency p95 within SLO",
                "No elevated 5xx in last 10m"
            ],
        }
    return plan


def process_incident(ch, method, properties, body):
    incident = json.loads(body)
    incident_id = incident.get("id", "unknown")
    print(f"Planner: Processing incident {incident_id}")

    try:
        plan = generate_plan_with_gemini(incident)
        # Ensure required fields
        plan.setdefault("id", f"plan_{incident_id}")
        plan.setdefault("incident_id", incident_id)
        plan.setdefault("status", "proposed")
        plan.setdefault("title", f"Plan for {incident.get('title', 'Incident')}")

        # Publish plan
        ch.basic_publish(
            exchange="plans",
            routing_key="proposed",
            body=json.dumps(plan).encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
        print(f"Planner: Published plan {plan['id']}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        print(f"Planner: Error generating plan for {incident_id}: {exc}")
        # Nack and requeue to avoid message loss, but prevent tight loops
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


# Initialize RabbitMQ channel lazily so the app can start even if RabbitMQ is down
_channel = None


def start_consumer_background():
    global _channel
    if _channel is not None:
        return
    _channel = create_rabbitmq_channel(RABBITMQ_URL)
    _channel.basic_qos(prefetch_count=1)
    _channel.basic_consume(queue="q.incidents.new", on_message_callback=process_incident)
    threading.Thread(target=_channel.start_consuming, daemon=True).start()


@app.on_event("startup")
def on_startup():
    # Attempt to start consumer; if it fails, keep API up
    try:
        start_consumer_background()
        print("Planner: Consumer started")
    except Exception as exc:
        print(f"Planner: Failed to start consumer: {exc}")


@app.get("/")
def root():
    return {"message": "Planner Agent is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/plan/preview")
def preview_plan(incident: Dict[str, Any]):
    """Generate a plan without publishing to RabbitMQ (for testing)."""
    plan = generate_plan_with_gemini(incident)
    return plan


if __name__ == "__main__":
    # Start FastAPI (consumer starts on startup event)
    uvicorn.run(app, host="0.0.0.0", port=8001)
