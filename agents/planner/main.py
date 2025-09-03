import json
import os
import threading
from typing import Any, Dict, List, Optional

import pika
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field
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
    # incident is expected to be normalized already by normalize_incident()
    title = incident.get("title", "Unknown Incident")
    service = incident.get("affected_service", "unknown-service")

    return (
        "SYSTEM: You are the Planner agent in an incident-response platform for Kubernetes. "
        "Given the fully normalized incident JSON below, produce STRICT JSON ONLY (no markdown, no text outside JSON). "
        "Output schema must be: {id, incident_id, status, risk_level, title, summary, rationale, steps:[{action,target,cmd,notes}], rollout, verification:[string]}."
        " Keep commands short and safe, include rollback/verification."
        f"\n\nCONTEXT:\nService: {service}\nTitle: {title}"
        "\n\nINCIDENT_NORMALIZED_JSON:\n" + json.dumps(incident, ensure_ascii=False) +
        "\n\nREQUIREMENTS:\n- Prefer reversible actions first.\n- Include pre-checks and post-verification.\n- Never include markdown. JSON only."
    )


# ---------- Input models & normalization ----------
class LogEntry(BaseModel):
    timestamp: Optional[str] = None
    level: Optional[str] = None  # error|warn|info|debug
    message: str
    source: Optional[str] = None  # loki|app|k8s|system
    pod: Optional[str] = None
    container: Optional[str] = None
    namespace: Optional[str] = None


class MetricsSummary(BaseModel):
    cpu_usage: Optional[float] = Field(default=None, description="CPU usage percent")
    memory_usage: Optional[float] = Field(default=None, description="Memory usage percent")
    error_rate: Optional[float] = None
    latency_p95_ms: Optional[float] = None
    request_rate_rps: Optional[float] = None
    additional: Dict[str, Any] = Field(default_factory=dict)


class K8sEvent(BaseModel):
    reason: Optional[str] = None
    message: Optional[str] = None
    type: Optional[str] = None  # Warning|Normal
    involved_object: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None


class GitCommit(BaseModel):
    sha: Optional[str] = None
    message: Optional[str] = None
    author: Optional[str] = None
    timestamp: Optional[str] = None
    files_changed: Optional[int] = None


class IncidentModel(BaseModel):
    id: str
    title: Optional[str] = None
    affected_service: Optional[str] = None
    hypothesis: Optional[str] = None
    symptoms: Optional[List[str]] = None
    metrics: Optional[Dict[str, Any]] = None
    logs: Optional[List[Dict[str, Any]]] = None
    loki_logs: Optional[List[Dict[str, Any]]] = None
    app_logs: Optional[List[Dict[str, Any]]] = None
    k8s_events: Optional[List[Dict[str, Any]]] = None
    git_commits: Optional[List[Dict[str, Any]]] = None


def _coerce_level(msg: str, level: Optional[str]) -> str:
    lvl = (level or "").lower()
    if any(x in msg.lower() for x in ["exception", "panic", "fatal", "stacktrace", "error", "err "]):
        return "error"
    if any(x in msg.lower() for x in ["warn", "warning", "timeout", "retry"]):
        return "warn"
    if lvl in {"error", "warn", "info", "debug"}:
        return lvl
    return "info"


def normalize_incident(raw: IncidentModel) -> Dict[str, Any]:
    # Logs: merge sources and classify levels
    merged_logs: List[LogEntry] = []
    for src_key, src_name in (
        (raw.logs, None),
        (raw.loki_logs, "loki"),
        (raw.app_logs, "app"),
    ):
        if not src_key:
            continue
        for entry in src_key:
            msg = entry.get("message") or entry.get("msg") or json.dumps(entry)
            le = LogEntry(
                timestamp=entry.get("ts") or entry.get("timestamp"),
                level=_coerce_level(msg, entry.get("level")),
                message=msg,
                source=entry.get("source") or src_name,
                pod=entry.get("pod"),
                container=entry.get("container"),
                namespace=entry.get("namespace"),
            )
            merged_logs.append(le)

    # K8s events
    k8s_events: List[K8sEvent] = []
    if raw.k8s_events:
        for ev in raw.k8s_events:
            k8s_events.append(K8sEvent(**{k: ev.get(k) for k in ["reason", "message", "type", "involved_object", "timestamp"]}))

    # Metrics summary
    m = raw.metrics or {}
    metrics = MetricsSummary(
        cpu_usage=m.get("cpu_usage"),
        memory_usage=m.get("memory_usage"),
        error_rate=m.get("error_rate"),
        latency_p95_ms=m.get("latency_p95_ms"),
        request_rate_rps=m.get("request_rate_rps"),
        additional={k: v for k, v in m.items() if k not in {"cpu_usage", "memory_usage", "error_rate", "latency_p95_ms", "request_rate_rps"}},
    )

    # Git commits
    commits: List[GitCommit] = []
    if raw.git_commits:
        for c in raw.git_commits:
            commits.append(GitCommit(**{k: c.get(k) for k in ["sha", "message", "author", "timestamp", "files_changed"]}))

    # Heuristic severity
    high_error = metrics.error_rate is not None and metrics.error_rate >= 0.05
    high_latency = metrics.latency_p95_ms is not None and metrics.latency_p95_ms >= 800
    error_logs = sum(1 for l in merged_logs if l.level == "error")
    severity = "high" if (high_error or high_latency or error_logs > 5) else ("medium" if error_logs > 0 else "low")

    normalized = {
        "id": raw.id,
        "title": raw.title,
        "affected_service": raw.affected_service,
        "hypothesis": raw.hypothesis,
        "symptoms": raw.symptoms or [],
        "metrics_summary": metrics.model_dump(),
        "logs": [le.model_dump() for le in merged_logs[:200]],  # cap to avoid huge prompts
        "k8s_events": [ev.model_dump() for ev in k8s_events[:100]],
        "git_commits": [gc.model_dump() for gc in commits[:50]],
        "derived": {"severity": severity, "error_log_count": error_logs},
    }
    return normalized


def generate_plan_with_gemini(incident: Dict[str, Any]) -> Dict[str, Any]:
    model = ensure_gemini_client()
    prompt = build_planner_prompt(incident)
    # Best-effort call; SDK does not expose timeout directly, so rely on default client behavior.
    response = model.generate_content(prompt)
    text = response.text if hasattr(response, "text") else str(response)

    # Try parsing JSON from the model; if it fails, fallback to simple plan
    # Accept JSON optionally wrapped in markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # strip leading ```lang and trailing ```
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
    # Try direct parse first
    try:
        return json.loads(cleaned)
    except Exception:
        # Try to extract first JSON object
        import re
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            candidate = m.group(0)
            try:
                return json.loads(candidate)
            except Exception:
                pass
        raise ValueError(f"LLM returned non-JSON: {text[:500]}")


@app.get("/diagnostics/gemini")
def diagnostics_gemini():
    try:
        model = ensure_gemini_client()
        # Lightweight call to validate credentials/model
        _ = model.count_tokens("ping")
        return {"ok": True, "model": GEMINI_MODEL}
    except Exception as exc:
        return {"ok": False, "model": GEMINI_MODEL, "error": str(exc)}


def process_incident(ch, method, properties, body):
    incoming = json.loads(body)
    try:
        raw = IncidentModel(**incoming)
    except Exception:
        # Accept unknown shapes but still try to process
        raw = IncidentModel(id=incoming.get("id", "unknown"),
                            title=incoming.get("title"),
                            affected_service=incoming.get("affected_service"),
                            hypothesis=incoming.get("hypothesis"),
                            symptoms=incoming.get("symptoms"),
                            metrics=incoming.get("metrics"),
                            logs=incoming.get("logs"),
                            loki_logs=incoming.get("loki_logs"),
                            app_logs=incoming.get("app_logs"),
                            k8s_events=incoming.get("k8s_events"),
                            git_commits=incoming.get("git_commits"))
    incident = normalize_incident(raw)
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
def preview_plan(incident: IncidentModel):
    """Generate a plan without publishing to RabbitMQ (for testing)."""
    normalized = normalize_incident(incident)
    try:
        return generate_plan_with_gemini(normalized)
    except Exception as exc:
        # No fallback plan; return structured error for caller
        return {"error": "planner_llm_error", "detail": str(exc)}


if __name__ == "__main__":
    # Start FastAPI (consumer starts on startup event)
    uvicorn.run(app, host="0.0.0.0", port=8001)
