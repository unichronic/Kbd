import os
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client.slack_agent_db

incidents_collection = db.incidents
alerts_collection = db.alerts
triggers_collection = db.triggers

def get_incident_data(incident_id: str, field: str):
    """Retrieve a specific field or the entire incident document."""
    incident = incidents_collection.find_one({"incident_id": incident_id})

    if not incident:
        return f"Incident {incident_id} not found."

    if field == "incident":
        # Format the whole incident for display
        import json
        # Remove non-serializable _id before sending
        incident.pop('_id', None)
        return json.dumps(incident, indent=2)

    return incident.get(field, f"{field.capitalize()} not found for incident {incident_id}")

def get_recent_alerts():
    """Retrieve the last 5 alerts."""
    alerts = list(alerts_collection.find().sort("timestamp", -1).limit(5))
    if not alerts:
        return "No recent alerts found."
    
    response = "Recent Alerts:\n"
    for alert in alerts:
        response += f"- {alert.get('alert_name')}: {alert.get('status')}\n"
    return response

def get_filtered_alerts(filter_type: str):
    """Retrieve alerts based on filter type."""
    if filter_type == "critical":
        alerts = list(alerts_collection.find({"severity": "critical"}).sort("timestamp", -1))
        title = "Critical Alerts"
    elif filter_type == "warning":
        alerts = list(alerts_collection.find({"severity": "warning"}).sort("timestamp", -1))
        title = "Warning Alerts"
    elif filter_type == "firing":
        alerts = list(alerts_collection.find({"status": "firing"}).sort("timestamp", -1))
        title = "Firing Alerts"
    elif filter_type == "resolved":
        alerts = list(alerts_collection.find({"status": "resolved"}).sort("timestamp", -1))
        title = "Resolved Alerts"
    elif filter_type.isdigit():
        # Get alerts from last X days
        days = int(filter_type)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_string = cutoff_date.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        alerts = list(alerts_collection.find({
            "timestamp": {
                "$gte": cutoff_string
            }
        }).sort("timestamp", -1))
        title = f"Alerts from last {days} days"
    else:
        return f"Unknown alert filter: {filter_type}"
    
    if not alerts:
        return f"No {title.lower()} found."
    
    response = f"{title}:\n"
    for alert in alerts:
        severity = alert.get('severity', 'unknown')
        source = alert.get('source', 'unknown')
        response += f"- {alert.get('alert_name')} ({severity}) from {source} - Status: {alert.get('status')}\n"
    return response

def get_prometheus_metrics(query_type: str = "basic"):
    """Query Prometheus for system metrics."""
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    
    try:
        if query_type == "cpu":
            # Try multiple CPU queries with fallbacks
            cpu_queries = [
                # Standard node_exporter CPU usage (5m average)
                "100 - (avg by(instance) (irate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
                # Alternative CPU query
                "100 - (avg(irate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
                # Simple CPU query without averaging
                "node_cpu_seconds_total",
                # Fallback to any CPU-related metric
                "up{job=~\".*node.*\"}"
            ]
            
            for i, query in enumerate(cpu_queries):
                response = requests.get(f"{prometheus_url}/api/v1/query", params={"query": query}, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "success" and data["data"]["result"]:
                        result_text = f"Prometheus CPU Metrics (query {i+1}):\n"
                        for result in data["data"]["result"]:
                            instance = result["metric"].get("instance", "unknown")
                            job = result["metric"].get("job", "unknown")
                            value = result["value"][1]
                            if i == 0 or i == 1:  # CPU percentage queries
                                result_text += f"- {instance} ({job}): {float(value):.2f}%\n"
                            else:  # Raw metrics
                                result_text += f"- {instance} ({job}): {value}\n"
                        return result_text
            
            return "No CPU metrics found. Node exporter may not be running or configured."
            
        elif query_type == "memory":
            # Memory usage query with fallbacks
            memory_queries = [
                "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
                "node_memory_MemTotal_bytes",
                "up{job=~\".*node.*\"}"
            ]
            
            for query in memory_queries:
                response = requests.get(f"{prometheus_url}/api/v1/query", params={"query": query}, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "success" and data["data"]["result"]:
                        break
            else:
                return "No memory metrics found."
                
        elif query_type == "disk":
            # Disk usage query with fallbacks
            disk_queries = [
                "(1 - (node_filesystem_avail_bytes{fstype!=\"tmpfs\"} / node_filesystem_size_bytes{fstype!=\"tmpfs\"})) * 100",
                "node_filesystem_size_bytes",
                "up{job=~\".*node.*\"}"
            ]
            
            for query in disk_queries:
                response = requests.get(f"{prometheus_url}/api/v1/query", params={"query": query}, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "success" and data["data"]["result"]:
                        break
            else:
                return "No disk metrics found."
                
        else:
            # Basic health check
            response = requests.get(f"{prometheus_url}/api/v1/query", params={"query": "up"}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "success":
                if data["data"]["result"]:
                    result_text = f"Prometheus {query_type.capitalize()} Metrics:\n"
                    for result in data["data"]["result"]:
                        instance = result["metric"].get("instance", "unknown")
                        job = result["metric"].get("job", "unknown")
                        value = result["value"][1]
                        if query_type in ["memory", "disk"] and "percentage" not in str(query):
                            # Show percentage for memory/disk if it's the percentage query
                            result_text += f"- {instance} ({job}): {float(value):.2f}%\n"
                        else:
                            result_text += f"- {instance} ({job}): {value}\n"
                    return result_text
                else:
                    return f"No {query_type} metrics found. Prometheus is connected but no data returned. Try checking available metrics with '/get pod_status list'."
            else:
                return f"Prometheus query error: {data.get('error', 'Unknown error')}"
        else:
            return f"Prometheus query failed: HTTP {response.status_code}"
            
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to Prometheus: {str(e)}"

def get_available_metrics():
    """Get list of available metrics from Prometheus."""
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    
    try:
        response = requests.get(f"{prometheus_url}/api/v1/label/__name__/values", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "success":
                all_metrics = data["data"]
                
                # Filter for common system metrics
                cpu_metrics = [m for m in all_metrics if "cpu" in m.lower()]
                memory_metrics = [m for m in all_metrics if "memory" in m.lower() or "mem" in m.lower()]
                disk_metrics = [m for m in all_metrics if "disk" in m.lower() or "filesystem" in m.lower()]
                node_metrics = [m for m in all_metrics if "node_" in m.lower()]
                
                result = f"Available Prometheus metrics summary:\n"
                result += f"Total metrics: {len(all_metrics)}\n\n"
                
                if cpu_metrics:
                    result += f"CPU-related metrics ({len(cpu_metrics)}):\n"
                    result += "\n".join([f"- {metric}" for metric in cpu_metrics[:10]]) + "\n\n"
                
                if memory_metrics:
                    result += f"Memory-related metrics ({len(memory_metrics)}):\n"
                    result += "\n".join([f"- {metric}" for metric in memory_metrics[:10]]) + "\n\n"
                
                if disk_metrics:
                    result += f"Disk/Filesystem metrics ({len(disk_metrics)}):\n"
                    result += "\n".join([f"- {metric}" for metric in disk_metrics[:10]]) + "\n\n"
                
                if node_metrics:
                    result += f"Node exporter metrics ({len(node_metrics)}):\n"
                    result += "\n".join([f"- {metric}" for metric in node_metrics[:15]]) + "\n\n"
                
                if not any([cpu_metrics, memory_metrics, disk_metrics, node_metrics]):
                    result += "No common system metrics found. First 20 available metrics:\n"
                    result += "\n".join([f"- {metric}" for metric in all_metrics[:20]])
                
                return result
            else:
                return f"Error getting metrics: {data.get('error', 'Unknown error')}"
        else:
            return f"Failed to get metrics: HTTP {response.status_code}"
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to Prometheus: {str(e)}"

def save_trigger(trigger_name: str, user_id: str):
    """Save a trigger-to-user mapping in the database."""
    triggers_collection.update_one(
        {"trigger_event_name": trigger_name},
        {"$set": {"slack_user_id_to_tag": user_id}},
        upsert=True
    )

def update_incident(incident_id: str, field: str, value: str):
    """Update a specific field in an incident document."""
    incidents_collection.update_one(
        {"incident_id": incident_id},
        {"$set": {field: value}}
    )

def get_user_for_trigger(trigger_name: str):
    """Retrieve the user ID for a given trigger name."""
    trigger = triggers_collection.find_one({"trigger_event_name": trigger_name})
    if trigger:
        return trigger.get("slack_user_id_to_tag")
    return None

def get_previous_incidents(days: int):
    """Retrieve incidents from the last n days."""
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=int(days))
        cutoff_string = cutoff_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    except (ValueError, TypeError):
        return "Invalid number of days provided."

    incidents = list(incidents_collection.find({
        "created_at": {
            "$gte": cutoff_string
        }
    }).sort("created_at", -1))

    if not incidents:
        return f"No incidents found in the last {days} days."

    response = f"Incidents from the last {days} days:\n"
    for incident in incidents:
        response += f"- {incident.get('incident_id')}: {incident.get('title')} ({incident.get('status')})\n"
    return response
