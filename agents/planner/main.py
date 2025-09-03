import json
import os
import threading
from typing import Any, Dict, List, Optional

import pika
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field
import uvicorn

# Import new modular components
from context.gatherer import ContextGatherer
from core.planner_engine import PlannerEngine
from models.incident import LogEntry, MetricsSummary, K8sEvent, GitCommit, IncidentModel
from models.context import EnrichedContext
from utils.retry_handler import RetryHandler

try:
    import google.generativeai as genai
except Exception:  # Library may not be installed yet during import-time in some environments
    genai = None  # type: ignore


app = FastAPI(title="Planner Agent")


# Configuration and setup
load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Context enrichment configuration
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
CHROMADB_URL = os.getenv("CHROMADB_URL", "http://localhost:8000")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GITHUB_REPO_OWNER = os.getenv("GITHUB_REPO_OWNER")
GITHUB_REPO_NAME = os.getenv("GITHUB_REPO_NAME")
CHROMADB_COLLECTION_NAME = os.getenv("CHROMADB_COLLECTION_NAME", "incident_history")
CHROMADB_EMBEDDING_MODEL = os.getenv("CHROMADB_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
WEB_SEARCH_TIMEOUT = int(os.getenv("WEB_SEARCH_TIMEOUT", "10"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.8"))


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


# ---------- Enhanced Planner Components ----------
# Global instances for context gathering and planning
context_gatherer: Optional[ContextGatherer] = None
planner_engine: Optional[PlannerEngine] = None


def initialize_enhanced_components():
    """Initialize the enhanced planner components."""
    global context_gatherer, planner_engine
    
    try:
        # Initialize context gatherer
        context_gatherer = ContextGatherer(
            loki_url=LOKI_URL,
            chromadb_host="localhost",
            chromadb_port=8000,
            github_token=GITHUB_TOKEN,
            github_repo_owner=GITHUB_REPO_OWNER,
            github_repo_name=GITHUB_REPO_NAME,
            tavily_api_key=TAVILY_API_KEY,
            chromadb_collection=CHROMADB_COLLECTION_NAME,
            chromadb_embedding_model=CHROMADB_EMBEDDING_MODEL
        )
        
        # Initialize planner engine
        planner_engine = PlannerEngine(
            model_name=GEMINI_MODEL,
            temperature=0.0
        )
        
        print("Enhanced Planner: Components initialized successfully")
        
    except Exception as e:
        print(f"Enhanced Planner: Error initializing components: {e}")
        # Fall back to basic components
        context_gatherer = None
        planner_engine = None


def get_plan_type(incident_data: Dict[str, Any]) -> str:
    """Determine the appropriate plan type based on incident characteristics."""
    severity = incident_data.get('derived', {}).get('severity', 'low')
    error_log_count = incident_data.get('derived', {}).get('error_log_count', 0)
    
    # Quick plan for urgent incidents
    if severity == 'high' and error_log_count > 10:
        return 'quick'
    
    # Deep dive for complex incidents
    if severity == 'high' and error_log_count > 5:
        return 'deep_dive'
    
    # Comprehensive plan for most incidents
    return 'comprehensive'


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


@app.get("/diagnostics/enhanced")
async def diagnostics_enhanced():
    """Diagnostic endpoint for enhanced planner components."""
    try:
        diagnostics = {
            "enhanced_components": {
                "context_gatherer": context_gatherer is not None,
                "planner_engine": planner_engine is not None
            },
            "configuration": {
                "loki_url": LOKI_URL,
                "chromadb_url": f"http://localhost:8000",
                "github_configured": GITHUB_TOKEN is not None,
                "web_search_configured": TAVILY_API_KEY is not None
            }
        }
        
        # Get context gatherer stats if available
        if context_gatherer:
            try:
                context_stats = await context_gatherer.get_context_stats()
                diagnostics["context_stats"] = context_stats
            except Exception as e:
                diagnostics["context_stats"] = {"error": str(e)}
        
        return diagnostics
        
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/diagnostics/context")
async def diagnostics_context():
    """Test context gathering capabilities."""
    if not context_gatherer:
        return {"error": "Context gatherer not initialized"}
    
    try:
        # Create a test incident
        test_incident = {
            "id": "test_incident",
            "title": "Test incident for diagnostics",
            "affected_service": "test-service",
            "hypothesis": "Testing context gathering",
            "symptoms": ["Service not responding"],
            "derived": {"severity": "low", "error_log_count": 0}
        }
        
        # Test context gathering
        context = await context_gatherer.gather_all_context(
            test_incident, 
            confidence_threshold=CONFIDENCE_THRESHOLD
        )
        
        return {
            "test_incident": test_incident,
            "context_gathered": {
                "loki_logs_count": len(context.loki_logs),
                "similar_incidents_count": len(context.similar_incidents),
                "recent_commits_count": len(context.recent_commits),
                "web_knowledge_count": len(context.web_knowledge),
                "sources_used": [source.value for source in context.sources_used],
                "gathering_time_ms": context.gathering_time_ms,
                "errors": context.gathering_errors
            }
        }
        
    except Exception as exc:
        return {"error": str(exc)}


async def process_incident_enhanced(ch, method, properties, body):
    """Enhanced incident processing with context enrichment."""
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
    print(f"Enhanced Planner: Processing incident {incident_id} with context enrichment")

    try:
        # Determine plan type based on incident characteristics
        plan_type = get_plan_type(incident)
        print(f"Enhanced Planner: Using {plan_type} plan type for incident {incident_id}")
        
        # Gather enriched context if components are available
        enriched_context = None
        if context_gatherer:
            try:
                enriched_context = await context_gatherer.gather_all_context(
                    incident, 
                    parallel=True, 
                    confidence_threshold=CONFIDENCE_THRESHOLD
                )
                print(f"Enhanced Planner: Gathered context from {len(enriched_context.sources_used)} sources")
            except Exception as e:
                print(f"Enhanced Planner: Context gathering failed: {e}")
                enriched_context = None
        
        # Generate plan using enhanced engine if available
        if planner_engine and enriched_context:
            if plan_type == 'quick':
                plan = await planner_engine.generate_quick_plan(incident, enriched_context)
            elif plan_type == 'deep_dive':
                plan = await planner_engine.generate_deep_dive_plan(incident, enriched_context)
            else:
                plan = await planner_engine.generate_comprehensive_plan(incident, enriched_context)
        else:
            # Fall back to original plan generation
            print(f"Enhanced Planner: Falling back to basic plan generation")
            plan = generate_plan_with_gemini(incident)
        
        # Ensure required fields
        plan.setdefault("id", f"plan_{incident_id}")
        plan.setdefault("incident_id", incident_id)
        plan.setdefault("status", "proposed")
        plan.setdefault("title", f"Plan for {incident.get('title', 'Incident')}")
        
        # Add enhanced metadata
        if enriched_context:
            plan.setdefault("metadata", {}).update({
                "context_sources": [source.value for source in enriched_context.sources_used],
                "gathering_time_ms": enriched_context.gathering_time_ms,
                "plan_type": plan_type,
                "enhanced": True
            })
        
        # Store incident for future reference if context gatherer is available
        if context_gatherer and enriched_context:
            try:
                await context_gatherer.store_incident_for_future_reference(incident)
            except Exception as e:
                print(f"Enhanced Planner: Failed to store incident for future reference: {e}")

        # Publish plan
        ch.basic_publish(
            exchange="plans",
            routing_key="proposed",
            body=json.dumps(plan).encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
        print(f"Enhanced Planner: Published {plan_type} plan {plan['id']}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as exc:
        print(f"Enhanced Planner: Error generating plan for {incident_id}: {exc}")
        # Nack and requeue to avoid message loss, but prevent tight loops
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def process_incident(ch, method, properties, body):
    """Wrapper to run async incident processing."""
    import asyncio
    
    # Create new event loop for this thread if needed
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Run the async function
    loop.run_until_complete(process_incident_enhanced(ch, method, properties, body))


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
    # Initialize enhanced components
    initialize_enhanced_components()
    
    # Attempt to start consumer; if it fails, keep API up
    try:
        start_consumer_background()
        print("Enhanced Planner: Consumer started")
    except Exception as exc:
        print(f"Enhanced Planner: Failed to start consumer: {exc}")


@app.get("/")
def root():
    return {"message": "Planner Agent is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/plan/preview")
async def preview_plan(incident: IncidentModel):
    """Generate a plan without publishing to RabbitMQ (for testing)."""
    normalized = normalize_incident(incident)
    
    try:
        # Use enhanced planning if available
        if context_gatherer and planner_engine:
            # Gather context
            enriched_context = await context_gatherer.gather_all_context(
                normalized, 
                parallel=True, 
                confidence_threshold=CONFIDENCE_THRESHOLD
            )
            
            # Determine plan type
            plan_type = get_plan_type(normalized)
            
            # Generate plan
            if plan_type == 'quick':
                plan = await planner_engine.generate_quick_plan(normalized, enriched_context)
            elif plan_type == 'deep_dive':
                plan = await planner_engine.generate_deep_dive_plan(normalized, enriched_context)
            else:
                plan = await planner_engine.generate_comprehensive_plan(normalized, enriched_context)
            
            # Add metadata
            plan.setdefault("metadata", {}).update({
                "context_sources": [source.value for source in enriched_context.sources_used],
                "gathering_time_ms": enriched_context.gathering_time_ms,
                "plan_type": plan_type,
                "enhanced": True,
                "preview": True
            })
            
            return plan
        else:
            # Fall back to basic planning
            return generate_plan_with_gemini(normalized)
            
    except Exception as exc:
        # No fallback plan; return structured error for caller
        return {"error": "planner_llm_error", "detail": str(exc)}


if __name__ == "__main__":
    print("Planner: Starting to consume incidents...")
    # Start FastAPI (consumer starts on startup event)
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
