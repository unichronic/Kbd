import os
import json
import httpx
from typing import Any, Dict, List
from pydantic import BaseModel, Field, ValidationError
import re

# Only these tools are allowed to be generated
ALLOWED_TOOLS = {"shell.run", "http.request", "compose.run", "fs.write", "kubectl.run"}

SYSTEM_PROMPT = SYSTEM_PROMPT = """You are an expert SRE agent that converts natural language instructions into precise JSON tool calls for system operations.

## CRITICAL RULES:
1. Output ONLY valid JSON in this exact format: {"steps":[...]}
2. NO explanations, comments, or text outside the JSON
3. Use ONLY these allowed tools: shell.run, http.request, compose.run, fs.write, kubectl.run
4. Always include at least one step
5. Environment is Windows - use cmd for shell operations

## TOOL SPECIFICATIONS:

### shell.run
Purpose: Execute shell commands on Windows
Required args: {"cmd": "cmd", "args": ["/c", "command", "param1", "param2"]}
Optional: {"cwd": "C:\\path\\to\\directory", "env": {"VAR": "value"}}
Use for: Windows commands, local operations requiring filesystem context

### kubectl.run  
Purpose: Kubernetes cluster operations
Required args: {"args": ["verb", "resource", "flags"]}
NEVER include "cwd" - kubectl operates on cluster, not local filesystem
Use for: All Kubernetes operations (deploy, scale, restart, status checks)

### http.request
Purpose: HTTP API calls
Required args: {"method": "GET/POST/PUT/DELETE", "url": "https://example.com"}
Optional: {"json": {...}, "headers": {...}}
NEVER include "cwd" - HTTP calls don't need filesystem context

### compose.run
Purpose: Docker Compose operations
Required args: {"args": ["up", "down", "restart", "etc"]}
Optional: {"cwd": "path\\to\\compose\\files"} (only if compose files not in default location)

### fs.write
Purpose: Write files to disk
Required args: {"path": "filename.txt", "content": "file contents"}
Optional: {"cwd": "directory\\path"}

## OPERATION PATTERNS:

Kubernetes deployment restart:
{"steps":[
  {"tool":"kubectl.run","args":{"args":["rollout","restart","deployment/NAME","-n","NAMESPACE"]}},
  {"tool":"kubectl.run","args":{"args":["rollout","status","deployment/NAME","-n","NAMESPACE"]}}
]}

Scale Kubernetes deployment:
{"steps":[
  {"tool":"kubectl.run","args":{"args":["scale","deployment/NAME","--replicas=N","-n","NAMESPACE"]}},
  {"tool":"kubectl.run","args":{"args":["rollout","status","deployment/NAME","-n","NAMESPACE"]}}
]}

Windows shell command:
{"steps":[
  {"tool":"shell.run","args":{"cmd":"cmd","args":["/c","dir","C:\\temp"]}}
]}

Create configuration file:
{"steps":[
  {"tool":"fs.write","args":{"path":"config.yaml","content":"apiVersion: v1\\nkind: ConfigMap"}}
]}

## EXAMPLES:

Input: "Restart the hello deployment in sandbox namespace"
Output: {"steps":[{"tool":"kubectl.run","args":{"args":["rollout","restart","deployment/hello","-n","sandbox"]}},{"tool":"kubectl.run","args":{"args":["rollout","status","deployment/hello","-n","sandbox"]}}]}

Input: "Scale web-app deployment to 5 replicas in production"
Output: {"steps":[{"tool":"kubectl.run","args":{"args":["scale","deployment/web-app","--replicas=5","-n","production"]}},{"tool":"kubectl.run","args":{"args":["rollout","status","deployment/web-app","-n","production"]}}]}

Input: "Check if nginx service is running using kubectl"
Output: {"steps":[{"tool":"kubectl.run","args":{"args":["get","service","nginx","-o","wide"]}}]}

Input: "Create a backup of the database using pg_dump"
Output: {"steps":[{"tool":"shell.run","args":{"cmd":"cmd","args":["/c","pg_dump","-h","localhost","-U","user","mydb",">","backup.sql"]}}]}

Remember: Output ONLY the JSON object. No additional text."""

class Step(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)

class CompiledPlan(BaseModel):
    steps: List[Step]

# 1) replace _openai_compatible_chat with better logging + fallback
def _openai_compatible_chat(messages: List[Dict[str, str]], model: str) -> str:
    base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if os.getenv("LLM_HTTP_REFERER"):
        headers["HTTP-Referer"] = os.getenv("LLM_HTTP_REFERER")
    if os.getenv("LLM_APP_TITLE"):
        headers["X-Title"] = os.getenv("LLM_APP_TITLE")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    with httpx.Client(timeout=30) as client:
        try:
            r = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            if r.status_code == 400:
                # Fallback: retry without response_format for models that don’t support it
                fallback = payload.copy()
                fallback.pop("response_format", None)
                r2 = client.post(f"{base_url}/chat/completions", json=fallback, headers=headers)
                r2.raise_for_status()
                data2 = r2.json()
                content2 = data2["choices"][0]["message"]["content"]
                return content2
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            body = e.response.text if e.response is not None else ""
            raise RuntimeError(f"LLM call failed ({e.response.status_code if e.response else 'n/a'}): {body}") from e

# Replace/extend _normalize_steps_object to scrub cwd and accept one-key objects
def _normalize_steps_object(data: dict) -> dict:
    steps = data.get("steps", [])
    normalized = []
    for s in steps:
        if isinstance(s, dict):
            if "tool" in s:
                s.setdefault("args", {})
                # Remove bogus/placeholder cwd
                if s["args"].get("cwd") in ("relative\\path", "relative/path", ""):
                    s["args"].pop("cwd", None)
                # Remove cwd for non-FS tools
                if s["tool"] in ("kubectl.run", "http.request", "compose.run"):
                    s["args"].pop("cwd", None)
                normalized.append(s)
            elif len(s) == 1:
                tool, args = next(iter(s.items()))
                args = args or {}
                # same cwd cleanup
                if args.get("cwd") in ("relative\\path", "relative/path", ""):
                    args.pop("cwd", None)
                if tool in ("kubectl.run", "http.request", "compose.run"):
                    args.pop("cwd", None)
                normalized.append({"tool": str(tool), "args": args})
    data["steps"] = normalized
    return data

def _rule_based_compile(instructions: str) -> dict | None:
    text = instructions.lower()
    ns = "sandbox"
    # restart deployment
    m = re.search(r"restart .*deployment\s+(\S+)", text)
    if m:
        dep = m.group(1)
        return {"steps": [
            {"tool":"kubectl.run","args":{"args":["rollout","restart",f"deployment/{dep}","-n",ns]}},
            {"tool":"kubectl.run","args":{"args":["rollout","status",f"deployment/{dep}","-n",ns]}}
        ]}
    # scale deployment to N
    m = re.search(r"scale .*deployment\s+(\S+).*(?:to|=)\s*(\d+)", text)
    if m:
        dep, n = m.group(1), m.group(2)
        return {"steps": [
            {"tool":"kubectl.run","args":{"args":["scale",f"deployment/{dep}",f"--replicas={n}","-n",ns]}},
            {"tool":"kubectl.run","args":{"args":["rollout","status",f"deployment/{dep}","-n",ns]}}
        ]}
    return None

# 2) after getting content, ensure we extract JSON even if wrapped
def nl_to_steps(instructions: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Compile natural-language 'instructions' into structured steps.
    Returns: {"steps": [{tool, args}, ...]}
    Raises on validation/allowlist errors.
    """
    ctx = context or {}
    user_prompt = f"Instructions:\n{instructions}\n\nContext:\n{json.dumps(ctx)}"
    model = os.getenv("LLM_MODEL", "meta-llama/llama-3.3-8b-instruct:free")

    print(f"LLM model: {model}")
    rb = _rule_based_compile(instructions)
    if rb:
        return rb
    try:
        content = _openai_compatible_chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
        )
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")

    # Try direct JSON parse; fallback to extracting a JSON object
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise ValueError(f"LLM output not JSON: {content[:300]}")
        data = json.loads(match.group(0))

    data = _normalize_steps_object(data)

    try:
        compiled = CompiledPlan(**data)
    except ValidationError as ve:
        raise ValueError(f"LLM output failed schema validation: {ve}") from ve

    for s in compiled.steps:
        if s.tool not in ALLOWED_TOOLS:
            raise ValueError(f"Tool '{s.tool}' not allowed")

    print(f"Compiled steps: {compiled.steps}")
    return {"steps": [s.model_dump() for s in compiled.steps]}
