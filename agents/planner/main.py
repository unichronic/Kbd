import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

import pika
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field
import uvicorn

# Import new modular components
try:
    from context.gatherer import ContextGatherer
    from core.planner_engine import PlannerEngine
    from models.incident import LogEntry, MetricsSummary, K8sEvent, GitCommit, IncidentModel
    from models.context import EnrichedContext
    from models.plan import PlanModel, PlanMetadata, PlanType
    from utils.retry_handler import RetryHandler
    from utils.mongodb_client import mongodb_storage
    from quota_manager import should_use_enhanced_planning_with_quota, record_planning_request, get_quota_status, get_quota_recommendations
except ImportError as e:
    print(f"Warning: Could not import enhanced components: {e}")
    print("Falling back to basic planner functionality")
    
    # Create minimal fallback classes
    from typing import List, Dict, Any, Optional
    from enum import Enum
    
    class ContextSource(Enum):
        LOKI = "loki"
        CHROMADB = "chromadb"
        GITHUB = "github"
        WEB_SEARCH = "web_search"
    
    class LogEntry(BaseModel):
        timestamp: Optional[str] = None
        level: str = "info"
        message: str
        source: Optional[str] = None
        pod: Optional[str] = None
        container: Optional[str] = None
        namespace: Optional[str] = None
    
    class MetricsSummary(BaseModel):
        cpu_usage: Optional[float] = None
        memory_usage: Optional[float] = None
        error_rate: Optional[float] = None
        latency_p95_ms: Optional[float] = None
        request_rate_rps: Optional[float] = None
        additional: Dict[str, Any] = Field(default_factory=dict)
    
    class K8sEvent(BaseModel):
        reason: Optional[str] = None
        message: Optional[str] = None
        type: Optional[str] = None
        involved_object: Optional[str] = None
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
        severity: Optional[str] = None
        metrics: Optional[Dict[str, Any]] = None
        logs: Optional[List[Dict[str, Any]]] = None
        loki_logs: Optional[List[Dict[str, Any]]] = None
        app_logs: Optional[List[Dict[str, Any]]] = None
        k8s_events: Optional[List[Dict[str, Any]]] = None
        git_commits: Optional[List[Dict[str, Any]]] = None
        # Prometheus alert specific fields
        labels: Optional[Dict[str, Any]] = None
        annotations: Optional[Dict[str, Any]] = None
        status: Optional[str] = None
        startsAt: Optional[str] = None
        endsAt: Optional[str] = None
        generatorURL: Optional[str] = None
        source: Optional[str] = None
        alert_rule: Optional[str] = None
        timestamp: Optional[str] = None
    
    class EnrichedContext(BaseModel):
        loki_logs: List[Dict[str, Any]] = Field(default_factory=list)
        similar_incidents: List[Any] = Field(default_factory=list)
        recent_commits: List[Dict[str, Any]] = Field(default_factory=list)
        web_knowledge: List[Dict[str, Any]] = Field(default_factory=list)
        sources_used: List[ContextSource] = Field(default_factory=list)
        gathering_time_ms: int = 0
        internal_confidence: float = 0.0
        web_search_triggered: bool = False
        web_search_reason: Optional[str] = None
        gathering_errors: Dict[ContextSource, str] = Field(default_factory=dict)
    
    # Set fallback classes
    ContextGatherer = None
    PlannerEngine = None
    RetryHandler = None

try:
    import google.generativeai as genai
except Exception:  # Library may not be installed yet during import-time in some environments
    genai = None  # type: ignore


app = FastAPI(title="Planner Agent")


# Configuration and setup
load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5673/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Context enrichment configuration
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
CHROMADB_URL = os.getenv("CHROMADB_URL", "http://localhost:8002")
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

# Simple request cache to avoid duplicate API calls
request_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def initialize_enhanced_components():
    """Initialize the enhanced planner components."""
    global context_gatherer, planner_engine
    
    # Check if enhanced components are available
    if ContextGatherer is None or PlannerEngine is None:
        print("Enhanced Planner: Enhanced components not available, using basic functionality")
        context_gatherer = None
        planner_engine = None
        return
    
    try:
        # Initialize context gatherer
        context_gatherer = ContextGatherer(
            loki_url=LOKI_URL,
            chromadb_host="localhost",
            chromadb_port=8002,
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
    """
    Determine the appropriate plan type based on incident characteristics.
    For Prometheus alerts, we use a simple approach:
    - All incidents get 'comprehensive' planning initially
    - The context gathering will determine if we need more investigation
    """
    # For Prometheus alerts, we always start with comprehensive planning
    # The context gathering will tell us if we need to dig deeper
    return 'comprehensive'


def should_use_enhanced_planning(incident_data: Dict[str, Any]) -> bool:
    """
    Determine if we should use enhanced planning (API calls) based on incident priority.
    For Prometheus alerts, we use a simple severity-based approach.
    """
    severity = incident_data.get('derived', {}).get('severity', 'low')
    service = incident_data.get('affected_service', '')
    
    # Always use enhanced planning for high-severity incidents
    if severity == 'high':
        return True
    
    # Use enhanced planning for critical services (regardless of severity)
    critical_services = ['user-service', 'payment-service', 'auth-service', 'api-gateway']
    if any(critical in service.lower() for critical in critical_services):
        return True
    
    # For medium/low severity on non-critical services, use basic planning to conserve quota
    return False


def get_context_priority(incident_data: Dict[str, Any]) -> Dict[str, bool]:
    """
    Determine which context sources to prioritize based on incident characteristics.
    For Prometheus alerts, we use a simple approach:
    - Always gather internal context (Loki, ChromaDB)
    - GitHub and Web Search are determined by confidence-based logic
    """
    severity = incident_data.get('derived', {}).get('severity', 'low')
    service = incident_data.get('affected_service', '')
    
    # Base priority - always use internal sources for Prometheus alerts
    priority = {
        'loki': True,      # Always get recent logs from Loki
        'chromadb': True,  # Always check historical incidents
        'github': False,   # Will be determined by confidence logic
        'web_search': False  # Will be determined by confidence logic
    }
    
    # High severity incidents get GitHub context (recent code changes)
    if severity == 'high':
        priority['github'] = True
    
    # Critical services get GitHub context (recent code changes)
    critical_services = ['user-service', 'payment-service', 'auth-service', 'api-gateway']
    if any(critical in service.lower() for critical in critical_services):
        priority['github'] = True
    
    # Web search is handled by confidence-based logic in the context gatherer
    # We don't pre-determine it here
    
    return priority


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

    # Heuristic severity - respect original severity if set, otherwise calculate
    original_severity = raw.severity
    
    if original_severity and original_severity in ['low', 'medium', 'high']:
        # Use original severity if it's valid
        severity = original_severity
    else:
        # Calculate severity based on metrics and logs
        high_error = metrics.error_rate is not None and metrics.error_rate >= 0.05
        high_latency = metrics.latency_p95_ms is not None and metrics.latency_p95_ms >= 800
        error_logs = sum(1 for l in merged_logs if l.level == "error")
        severity = "high" if (high_error or high_latency or error_logs > 5) else ("medium" if error_logs > 0 else "low")
    
    error_logs = sum(1 for l in merged_logs if l.level == "error")

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
    # Create cache key based on incident characteristics
    cache_key = f"{incident.get('id', 'unknown')}_{incident.get('title', '')}_{incident.get('affected_service', '')}"
    
    # Check cache first
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        cache_time = cached_data.get('timestamp', 0)
        current_time = time.time()
        
        if current_time - cache_time < CACHE_TTL_SECONDS:
            print(f"Enhanced Planner: Using cached plan for {incident.get('id', 'unknown')}")
            return cached_data['plan']
        else:
            # Remove expired cache entry
            del request_cache[cache_key]
    
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
        plan = json.loads(cleaned)
        # Cache the successful result
        request_cache[cache_key] = {
            'plan': plan,
            'timestamp': time.time()
        }
        return plan
    except Exception:
        # Try to extract first JSON object
        import re
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            candidate = m.group(0)
            try:
                plan = json.loads(candidate)
                # Cache the successful result
                request_cache[cache_key] = {
                    'plan': plan,
                    'timestamp': time.time()
                }
                return plan
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
                "chromadb_url": f"http://localhost:8002",
                "github_configured": GITHUB_TOKEN is not None,
                "web_search_configured": TAVILY_API_KEY is not None
            },
            "quota_management": {
                "cache_size": len(request_cache),
                "cache_ttl_seconds": CACHE_TTL_SECONDS,
                "cached_plans": list(request_cache.keys())
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


@app.get("/diagnostics/quota")
def diagnostics_quota():
    """Get quota usage and management information."""
    try:
        quota_status = get_quota_status()
        recommendations = get_quota_recommendations()
        
        return {
            "quota_status": quota_status,
            "recommendations": recommendations,
            "cache_info": {
                "cache_size": len(request_cache),
                "cache_ttl_seconds": CACHE_TTL_SECONDS,
                "cached_plans": list(request_cache.keys())
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
                            severity=incoming.get("severity"),
                            metrics=incoming.get("metrics"),
                            logs=incoming.get("logs"),
                            loki_logs=incoming.get("loki_logs"),
                            app_logs=incoming.get("app_logs"),
                            k8s_events=incoming.get("k8s_events"),
                            git_commits=incoming.get("git_commits"),
                            labels=incoming.get("labels"),
                            annotations=incoming.get("annotations"),
                            status=incoming.get("status"),
                            startsAt=incoming.get("startsAt"),
                            endsAt=incoming.get("endsAt"),
                            generatorURL=incoming.get("generatorURL"),
                            source=incoming.get("source"),
                            alert_rule=incoming.get("alert_rule"),
                            timestamp=incoming.get("timestamp"))
    
    incident = normalize_incident(raw)
    incident_id = incident.get("id", "unknown")
    print(f"Enhanced Planner: Processing incident {incident_id} with context enrichment")

    try:
        # Determine if we should use enhanced planning (API calls) with quota awareness
        use_enhanced = should_use_enhanced_planning_with_quota(incident, "normal")
        print(f"Enhanced Planner: Enhanced planning {'enabled' if use_enhanced else 'disabled'} for incident {incident_id}")
        
        # Show quota status
        quota_status = get_quota_status()
        print(f"Enhanced Planner: Quota status - {quota_status['daily_usage']}/{quota_status['daily_limit']} daily, {quota_status['hourly_usage']}/{quota_status['hourly_limit']} hourly")
        
        # Determine plan type based on incident characteristics
        plan_type = get_plan_type(incident)
        print(f"Enhanced Planner: Using {plan_type} plan type for incident {incident_id}")
        
        # Gather enriched context if components are available and enhanced planning is enabled
        enriched_context = None
        if context_gatherer and use_enhanced:
            try:
                # Get context priority based on incident characteristics
                context_priority = get_context_priority(incident)
                print(f"Enhanced Planner: Context priority: {context_priority}")
                
                print(f"Enhanced Planner: Starting context gathering for incident {incident_id}")
                print(f"Enhanced Planner: Available context sources:")
                print(f"  • Loki: {LOKI_URL}")
                print(f"  • ChromaDB: http://localhost:8002")
                print(f"  • GitHub: {'configured' if GITHUB_TOKEN else 'not configured'}")
                print(f"  • Web Search: {'configured' if TAVILY_API_KEY else 'not configured'}")
                
                enriched_context = await context_gatherer.gather_all_context(
                    incident, 
                    parallel=True, 
                    confidence_threshold=CONFIDENCE_THRESHOLD
                )
                
                # Detailed context gathering results
                print(f"Enhanced Planner: Context gathering completed in {enriched_context.gathering_time_ms}ms")
                print(f"Enhanced Planner: Sources used: {[source.value for source in enriched_context.sources_used]}")
                print(f"Enhanced Planner: Context results:")
                print(f"  • Loki logs: {len(enriched_context.loki_logs)} entries")
                print(f"  • Similar incidents: {len(enriched_context.similar_incidents)} found")
                print(f"  • Recent commits: {len(enriched_context.recent_commits)} found")
                print(f"  • Web knowledge: {len(enriched_context.web_knowledge)} entries")
                print(f"  • Internal confidence: {enriched_context.internal_confidence:.3f}")
                print(f"  • Web search triggered: {enriched_context.web_search_triggered}")
                if enriched_context.web_search_reason:
                    print(f"  • Web search reason: {enriched_context.web_search_reason}")
                
                # Show any errors
                if enriched_context.gathering_errors:
                    print(f"Enhanced Planner: Context gathering errors:")
                    for source, error in enriched_context.gathering_errors.items():
                        print(f"  • {source.value}: {error}")
                
            except Exception as e:
                print(f"Enhanced Planner: Context gathering failed: {e}")
                print(f"Enhanced Planner: Error type: {type(e).__name__}")
                import traceback
                print(f"Enhanced Planner: Traceback: {traceback.format_exc()}")
                enriched_context = None
        elif not use_enhanced:
            print(f"Enhanced Planner: Skipping context gathering to conserve API quota")
        
        # Generate plan using enhanced engine if available and enhanced planning is enabled
        if planner_engine and enriched_context and use_enhanced:
            if plan_type == 'quick':
                plan = await planner_engine.generate_quick_plan(incident, enriched_context)
            elif plan_type == 'deep_dive':
                plan = await planner_engine.generate_deep_dive_plan(incident, enriched_context)
            else:
                plan = await planner_engine.generate_comprehensive_plan(incident, enriched_context)
        else:
            # Fall back to original plan generation
            print(f"Enhanced Planner: Using basic plan generation (quota conservation)")
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

        # Record the planning request for quota tracking
        record_planning_request("plan_generation", "normal", True)

        # Publish plan
        ch.basic_publish(
            exchange="plans",
            routing_key="proposed",
            body=json.dumps(plan).encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
        print(f"Enhanced Planner: Published {plan_type} plan {plan['id']}")
        
        # Save plan to MongoDB
        try:
            # Create plan metadata
            plan_metadata = PlanMetadata(
                plan_type=PlanType(plan_type) if plan_type in ['quick', 'comprehensive', 'deep_dive'] else PlanType.COMPREHENSIVE,
                enhanced=enriched_context is not None,
                context_sources=plan.get('metadata', {}).get('context_sources', []),
                gathering_time_ms=plan.get('metadata', {}).get('gathering_time_ms'),
                model_used="gemini"
            )
            
            # Create structured plan model
            structured_plan = PlanModel(
                id=plan['id'],
                incident_id=plan['incident_id'],
                title=plan.get('title', f"Plan for {incident.get('title', 'Incident')}"),
                description=plan.get('description'),
                steps=[],  # Will be populated from plan steps if available
                risk_level=plan.get('risk_level', 'low'),
                status='proposed',
                metadata=plan_metadata,
                source='planner'
            )
            
            # Save to MongoDB
            if mongodb_storage.save_plan(structured_plan.to_dict()):
                print(f"Enhanced Planner: Plan {plan['id']} saved to MongoDB successfully")
            else:
                print(f"Enhanced Planner: Failed to save plan {plan['id']} to MongoDB")
                
        except Exception as e:
            print(f"Enhanced Planner: Error saving plan to MongoDB: {e}")
            # Don't fail the entire process if MongoDB save fails
        
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


# API endpoints for frontend integration
@app.get("/api/plans")
async def get_plans(limit: int = 50, status: Optional[str] = None, incident_id: Optional[str] = None):
    """Get plans from MongoDB with optional filtering."""
    try:
        if not mongodb_storage.is_connected():
            return {"error": "MongoDB not connected", "plans": []}
        
        if incident_id:
            plans = mongodb_storage.get_plans_by_incident(incident_id)
        else:
            plans = mongodb_storage.get_recent_plans(limit=limit)
        
        # Filter by status if provided
        if status:
            plans = [plan for plan in plans if plan.get("status") == status]
        
        return {"plans": plans, "count": len(plans)}
    except Exception as e:
        return {"error": str(e), "plans": []}


@app.get("/api/plans/{plan_id}")
async def get_plan(plan_id: str):
    """Get a specific plan by ID."""
    try:
        if not mongodb_storage.is_connected():
            return {"error": "MongoDB not connected"}
        
        plan = mongodb_storage.get_plan(plan_id)
        if plan:
            return {"plan": plan}
        else:
            return {"error": "Plan not found"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/incidents")
async def get_incidents(limit: int = 50):
    """Get incidents with their associated plans."""
    try:
        if not mongodb_storage.is_connected():
            return {"error": "MongoDB not connected", "incidents": []}
        
        # Get recent plans and group by incident
        plans = mongodb_storage.get_recent_plans(limit=limit * 2)  # Get more plans to ensure we have incidents
        
        # Group plans by incident_id
        incidents_dict = {}
        for plan in plans:
            incident_id = plan.get("incident_id")
            if incident_id:
                if incident_id not in incidents_dict:
                    incidents_dict[incident_id] = {
                        "incident_id": incident_id,
                        "title": plan.get("title", f"Incident {incident_id}"),
                        "plans": [],
                        "latest_plan": None,
                        "plan_count": 0
                    }
                
                incidents_dict[incident_id]["plans"].append(plan)
                incidents_dict[incident_id]["plan_count"] += 1
                
                # Keep track of the latest plan
                if not incidents_dict[incident_id]["latest_plan"] or \
                   plan.get("created_at", "") > incidents_dict[incident_id]["latest_plan"].get("created_at", ""):
                    incidents_dict[incident_id]["latest_plan"] = plan
        
        # Convert to list and sort by latest plan creation time
        incidents = list(incidents_dict.values())
        incidents.sort(key=lambda x: x["latest_plan"].get("created_at", "") if x["latest_plan"] else "", reverse=True)
        
        return {"incidents": incidents[:limit], "count": len(incidents)}
    except Exception as e:
        return {"error": str(e), "incidents": []}


@app.get("/api/incidents/{incident_id}/plans")
async def get_incident_plans(incident_id: str):
    """Get all plans for a specific incident."""
    try:
        if not mongodb_storage.is_connected():
            return {"error": "MongoDB not connected", "plans": []}
        
        plans = mongodb_storage.get_plans_by_incident(incident_id)
        return {"incident_id": incident_id, "plans": plans, "count": len(plans)}
    except Exception as e:
        return {"error": str(e), "plans": []}


@app.get("/api/stats")
async def get_stats():
    """Get statistics about plans and incidents."""
    try:
        if not mongodb_storage.is_connected():
            return {"error": "MongoDB not connected"}
        
        # Get recent plans for statistics
        recent_plans = mongodb_storage.get_recent_plans(limit=1000)
        
        # Calculate statistics
        stats = {
            "total_plans": len(recent_plans),
            "plans_by_status": {},
            "plans_by_type": {},
            "recent_activity": {
                "last_24h": 0,
                "last_7d": 0
            }
        }
        
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        for plan in recent_plans:
            # Count by status
            status = plan.get("status", "unknown")
            stats["plans_by_status"][status] = stats["plans_by_status"].get(status, 0) + 1
            
            # Count by type
            plan_type = plan.get("metadata", {}).get("plan_type", "unknown")
            stats["plans_by_type"][plan_type] = stats["plans_by_type"].get(plan_type, 0) + 1
            
            # Count recent activity
            created_at = plan.get("created_at")
            if created_at:
                try:
                    if isinstance(created_at, str):
                        created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        created_dt = created_at
                    
                    if created_dt >= last_24h:
                        stats["recent_activity"]["last_24h"] += 1
                    if created_dt >= last_7d:
                        stats["recent_activity"]["last_7d"] += 1
                except:
                    pass
        
        return {"stats": stats}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    print("Planner: Starting to consume incidents...")
    # Start FastAPI (consumer starts on startup event)
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
