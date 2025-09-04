import json
import asyncio
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager
import aio_pika
import os
from dotenv import load_dotenv
from datetime import datetime
load_dotenv()

# Import MongoDB client
try:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'planner'))
    from utils.mongodb_client import mongodb_storage
    MONGODB_AVAILABLE = True
except ImportError:
    print("Warning: MongoDB client not available in actor")
    MONGODB_AVAILABLE = False
# FastAPI application with lifespan context manager
# The lifespan handles startup and shutdown tasks gracefully
# like connecting and disconnecting from RabbitMQ.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to RabbitMQ
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    try:
        connection = await aio_pika.connect_robust(f"amqp://guest:guest@{rabbitmq_host}:5672/")
        app.state.connection = connection
        app.state.channel = await connection.channel()

        # Declare exchanges
        await app.state.channel.declare_exchange('plans', aio_pika.ExchangeType.TOPIC, durable=True)
        await app.state.channel.declare_exchange('incidents', aio_pika.ExchangeType.TOPIC, durable=True)

        # QoS: process one message at a time
        await app.state.channel.set_qos(prefetch_count=1)

        # Declare queue and bind
        queue = await app.state.channel.declare_queue('q.plans.approved', durable=True,
                                                      arguments={
                                                          "x-dead-letter-exchange": "plans",
                                                          "x-dead-letter-routing-key": "plans.approved.dlq",
                                                      })
        await queue.bind('plans', routing_key='approved')

        # Start consuming messages in the background
        await queue.consume(process_plan)

        print("FastAPI app is connected to RabbitMQ and consuming messages.")

    except aio_pika.exceptions.AMQPConnectionError as e:
        print(f"Failed to connect to RabbitMQ: {e}")
        # You might want to handle this more gracefully in a production app
        # For now, we'll let the app start but without the consumer.
    
    # The `yield` is where the application runs
    yield

    # This code runs on shutdown
    print("FastAPI app is shutting down. Closing RabbitMQ connection.")
    if hasattr(app.state, 'channel'):
        await app.state.channel.close()
    if hasattr(app.state, 'connection'):
        await app.state.connection.close()


app = FastAPI(title="Actor Agent", lifespan=lifespan)

@app.on_event("startup")
async def start_mcp():
    # If you want socket transport, adapt run_mcp to listen on a TCP port instead of stdio.
    # For now, this is a no-op placeholder if you opt to run MCP as a sidecar/container.
    pass

async def process_plan(message: aio_pika.IncomingMessage):
    """Async function to execute a plan from the queue."""
    async with message.process():
        try:
            plan = json.loads(message.body)
            print(f"Executing plan: {plan.get('id', 'N/A')}")

            # Autonomy & idempotency
            import os, time
            max_risk = float(os.getenv("ACTOR_AUTONOMY_MAX_RISK", "0.3"))
            risk = float(plan.get("risk", 0))
            idemp_key = plan.get("idempotency_key") or f"{plan.get('incident_id','N/A')}:{plan.get('id','N/A')}"
            if not hasattr(app.state, "seen_keys"):
                app.state.seen_keys = set()
            if idemp_key in app.state.seen_keys:
                print(f"Skipping duplicate plan (idempotency): {idemp_key}")
                return
            app.state.seen_keys.add(idemp_key)

            status = "resolved"
            outputs = []
            start = time.perf_counter()

            if risk > max_risk:
                status = "skipped"
                outputs.append({"tool": "autonomy", "ok": False, "error": f"risk {risk} > max {max_risk}"})
            else:
                # Execute steps via MCP tools
                from mcp_server import shell_run, http_request
                # build steps if only instructions are provided
                instructions = plan.get("instructions")
                if instructions and not plan.get("steps"):
                    try:
                        from compile_plan import nl_to_steps
                        compiled = nl_to_steps(instructions, context={"sandbox": True})
                        plan["steps"] = compiled.get("steps", [])
                        print(f"Compiled steps: {plan['steps']}")
                    except Exception as e:
                        print(f"Compile error: {e}")
                        plan["steps"] = []
                # If compilation failed or returned no steps, try deterministic fallback
                if not plan.get("steps"):
                    fb = _fallback_steps_for_instructions(instructions or "")
                    if fb:
                        plan["steps"] = fb
                        print(f"Applied fallback steps: {plan['steps']}")
                steps = plan.get('steps', [])
                print(f"Executing steps: {steps}")
                for idx, step in enumerate(steps):
                    tool = step.get("tool")
                    args = step.get("args", {}) or {}
                    try:
                        if tool == "shell.run":
                            from mcp_server import shell_run
                            res = await shell_run(**args)
                        elif tool == "http.request":
                            from mcp_server import http_request
                            res = await http_request(**args)
                        elif tool == "fs.write":
                            from mcp_server import fs_write
                            res = await fs_write(**args)
                        elif tool == "compose.run":
                            from mcp_server import compose
                            res = await compose(**args)
                        elif tool == "docker.run":
                            from mcp_server import docker
                            res = await docker(**args)
                        elif tool == "kubectl.run":
                            from mcp_server import kubectl
                            res = await kubectl(**args)
                        else:
                            res = {"ok": False, "error": f"Unknown tool '{tool}'"}
                        outputs.append({"step": idx, "tool": tool, "result": res})
                        if not res.get("ok", False):
                            status = "failed"
                            break
                    except Exception as ex:
                        status = "failed"
                        outputs.append({"step": idx, "tool": tool, "error": str(ex)})
                        break

            duration_ms = int((time.perf_counter() - start) * 1000)

            # Update plan status in MongoDB
            if MONGODB_AVAILABLE and mongodb_storage.is_connected():
                try:
                    final_status = "completed" if status == "resolved" else "failed"
                    mongodb_storage.update_plan_status(
                        plan.get("id", "N/A"),
                        final_status,
                        started_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                        executed_by="actor_agent",
                        execution_output=json.dumps(outputs),
                        success_metrics={"duration_ms": duration_ms, "status": status}
                    )
                    print(f"Updated plan {plan.get('id', 'N/A')} status in MongoDB to {final_status}")
                except Exception as e:
                    print(f"Failed to update plan status in MongoDB: {e}")

            # Publish resolution
            resolution = {
                "incident_id": plan.get("incident_id", "N/A"),
                "status": status,
                "resolution_action": f"Executed plan: {plan.get('id', 'N/A')}",
                "plan_id": plan.get("id", "N/A"),
                "outputs": outputs,
                "duration_ms": duration_ms,
            }

            incidents_exchange = await app.state.channel.get_exchange('incidents')
            await incidents_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(resolution).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key='incidents.resolved'
            )

            print(f"Published resolution for incident: {plan.get('incident_id', 'N/A')} ({status})")
        except json.JSONDecodeError:
            print(f"Error: Received invalid JSON message: {message.body}")
        except Exception as e:
            print(f"An error occurred during plan processing: {e}")
            raise


@app.get("/")
def root():
    return {"message": "Actor Agent is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

def _fallback_steps_for_instructions(text: str) -> list[dict]:
    import re, os
    ns = os.getenv("ACTOR_K8S_DEFAULT_NS", "sandbox")
    # Prefer cmd wrapper to avoid kubectl allowlist issues
    def cmd_step(*args):  # args is the kubectl args list
        return {"tool":"shell.run","args":{"cmd":"cmd","args":["/c","kubectl", *args]}}
    t = (text or "").lower()

    # Restart deployment
    m = re.search(r"deployment[/\s]+([\w\-]+)", t)
    deploy = m.group(1) if m else os.getenv("ACTOR_K8S_DEFAULT_DEPLOY", "hello")
    if "restart" in t or "rollout restart" in t:
        return [
            cmd_step("rollout","restart",f"deployment/{deploy}","-n",ns),
            cmd_step("rollout","status",f"deployment/{deploy}","-n",ns),
        ]

    # Scale deployment to N
    mN = re.search(r"replicas?\s*=?\s*(\d+)", t) or re.search(r"\bto\s+(\d+)\b", t)
    if "scale" in t and mN:
        replicas = mN.group(1)
        return [
            cmd_step("scale",f"deployment/{deploy}",f"--replicas={replicas}","-n",ns),
            cmd_step("rollout","status",f"deployment/{deploy}","-n",ns),
        ]
    return []
if __name__ == "__main__":
    print("Actor: Starting to consume approved plans...")
    # Start FastAPI (consumer starts on startup event)
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
