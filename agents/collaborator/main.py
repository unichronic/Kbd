from fastapi import FastAPI, Request, HTTPException, Form
from typing import Optional
import uvicorn
import os
from kubernetes import client, config
from database import get_incident_data, get_recent_alerts, save_trigger, update_incident, get_user_for_trigger, get_previous_incidents, get_filtered_alerts, get_prometheus_metrics, get_available_metrics
from executor import restart_service
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# Load Kubernetes configuration
try:
    config.load_incluster_config()  # For in-cluster configuration
except config.ConfigException:
    try:
        config.load_kube_config()  # For local development
    except config.ConfigException:
        raise Exception("Could not configure Kubernetes client")

k8s_core_v1 = client.CoreV1Api()

app = FastAPI(title="Collaborator Agent")

@app.post("/get")
async def get_command(text: Optional[str] = Form(None)):
    if not text:
        return {"text": "Please provide a subcommand. Usage: /get [pod_status|incident|summary|plan|alerts|alert|prev_incidents] [arguments]"}

    parts = text.split()
    subcommand = parts[0]
    args = parts[1:]

    if subcommand == "pod_status":
        if not args:
            # Show all pods if no specific pod name provided
            try:
                pods = k8s_core_v1.list_namespaced_pod(namespace="default")
                if not pods.items:
                    return {"text": "No pods found in default namespace"}
                
                response = "Pod Status Summary:\n"
                for pod in pods.items:
                    response += f"- {pod.metadata.name}: {pod.status.phase}\n"
                return {"text": response}
            except Exception as e:
                return {"text": f"Kubernetes cluster not available: {str(e)[:100]}..."}
        
        pod_name = args[0]
        if pod_name == "prometheus":
            # Find Prometheus pods
            try:
                pods = k8s_core_v1.list_namespaced_pod(namespace="default")
                prometheus_pods = [pod for pod in pods.items if "prometheus" in pod.metadata.name.lower()]
                
                if not prometheus_pods:
                    return {"text": "No Prometheus pods found in default namespace"}
                
                response = "Prometheus Pod Status:\n"
                for pod in prometheus_pods:
                    response += f"- {pod.metadata.name}: {pod.status.phase}\n"
                return {"text": response}
            except Exception as e:
                return {"text": f"Kubernetes cluster not available: {str(e)[:100]}..."}
        elif pod_name in ["metrics", "cpu", "memory", "disk", "list"]:
            # Query Prometheus metrics or list available metrics
            if pod_name == "list":
                data = get_available_metrics()
            else:
                data = get_prometheus_metrics(pod_name if pod_name != "metrics" else "basic")
            return {"text": data}
        else:
            # Specific pod name provided
            try:
                pod = k8s_core_v1.read_namespaced_pod_status(name=pod_name, namespace="default")
                return {"text": f"Status of pod '{pod_name}': {pod.status.phase}"}
            except Exception as e:
                return {"text": f"Kubernetes cluster not available: {str(e)[:100]}..."}
    
    elif subcommand in ["incident", "summary", "plan"]:
        if not args:
            return {"text": f"Please provide an incident ID. Usage: /get {subcommand} <incident-id>"}
        incident_id = args[0]
        data = get_incident_data(incident_id, subcommand)
        return {"text": data}

    elif subcommand == "alerts":
        alerts = get_recent_alerts()
        return {"text": alerts}
    
    elif subcommand == "alert":
        if not args:
            return {"text": "Usage: /get alert [critical|warning|firing|resolved|<days>]"}
        filter_type = args[0]
        if filter_type in ["critical", "warning", "firing", "resolved"] or filter_type.isdigit():
            data = get_filtered_alerts(filter_type)
            return {"text": data}
        else:
            return {"text": f"Unknown alert filter: {filter_type}. Usage: /get alert [critical|warning|firing|resolved|<days>]"}

    elif subcommand == "prev_incidents":
        if not args:
            return {"text": "Usage: /get prev_incidents <days_count>"}
        days_count = args[0]
        data = get_previous_incidents(days_count)
        return {"text": data}

    else:
        return {"text": f"Unknown subcommand: {subcommand}. Usage: /get [pod_status|incident|summary|plan|alerts|alert|prev_incidents]"}

@app.post("/set")
async def set_command(text: Optional[str] = Form(None)):
    if not text:
        return {"text": "Usage: /set <triggerNAME> <@user>"}

    parts = text.split()
    if len(parts) != 2:
        return {"text": "Invalid format. Usage: /set <triggerNAME> <@user>"}

    trigger_name, user_mention = parts
    
    try:
        # Extract user ID from mention
        user_id = user_mention.strip('<@>').split('|')[0]
        response = slack_client.users_info(user=user_id)
        if response["ok"]:
            user_id = response["user"]["id"]
            save_trigger(trigger_name, user_id)
            return {"text": f"Trigger '{trigger_name}' has been set to notify {user_mention}."}
        else:
            return {"text": "Invalid user mention."}
    except SlackApiError as e:
        return {"text": f"Error: {e.response['error']}"}

@app.post("/api/trigger")
async def handle_trigger(request: Request):
    data = await request.json()
    trigger_name = data.get("trigger_name")
    if not trigger_name:
        raise HTTPException(status_code=400, detail="'trigger_name' is required")

    user_id = get_user_for_trigger(trigger_name)
    if user_id:
        # In a real application, you would use the Slack client to send a message
        print(f"TRIGGER: Notifying user {user_id} for trigger '{trigger_name}'")
        return {"status": "notification sent"}
    else:
        print(f"TRIGGER: No user found for trigger '{trigger_name}'")
        return {"status": "no user configured"}

@app.post("/run")
async def run_command(text: Optional[str] = Form(None), user_id: Optional[str] = Form(None)):
    if not text:
        return {"text": "Usage: /run [plan|fix|restart] [arguments]"}

    parts = text.split()
    subcommand = parts[0]
    args = parts[1:]

    if subcommand in ["plan", "fix"]:
        if len(args) < 2:
            return {"text": f"Usage: /run {subcommand} <incident_id> <text>"}
        incident_id = args[0]
        update_text = " ".join(args[1:])
        update_incident(incident_id, subcommand, update_text)
        return {"text": f"Incident {incident_id} has been updated."}

    elif subcommand == "restart":
        if not args:
            return {"text": "Usage: /run restart <service_name>"}
        service_name = args[0]
        if not user_id:
            return {"text": "'user_id' is required for restart command."}

        try:
            slack_client.chat_postMessage(
                channel=user_id, # Post as a private message
                text=f"Do you want to restart the service '{service_name}'?",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Do you want to restart the service *{service_name}*?"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Confirm"},
                                "style": "primary",
                                "value": f"restart_confirm_{service_name}",
                                "action_id": "confirm_restart"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Cancel"},
                                "style": "danger",
                                "value": f"restart_cancel_{service_name}",
                                "action_id": "cancel_restart"
                            }
                        ]
                    }
                ]
            )
            return {"text": "Confirmation required. Please check your DMs."}
        except SlackApiError as e:
            return {"text": f"Error sending confirmation: {e.response['error']}"}

    else:
        return {"text": f"Unknown subcommand: {subcommand}"}

import json

@app.post("/slack/actions")
async def slack_actions(request: Request):
    form_data = await request.form()
    payload = json.loads(form_data.get("payload"))
    action_id = payload["actions"][0]["action_id"]
    value = payload["actions"][0]["value"]

    if action_id == "confirm_restart":
        service_name = value.replace("restart_confirm_", "")
        success, message = restart_service(service_name)
        response_text = f"Service '{service_name}' restarted successfully: {message}" if success else f"Failed to restart '{service_name}': {message}"
    elif action_id == "cancel_restart":
        service_name = value.replace("restart_cancel_", "")
        response_text = f"Restart of service '{service_name}' was cancelled."
    else:
        return

    # Update the original message
    response_url = payload["response_url"]
    import requests
    requests.post(response_url, json={"text": response_text, "replace_original": True})

    return

@app.get("/")
def root():
    return {"message": "Collaborator Agent is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
