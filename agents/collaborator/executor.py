import subprocess

def restart_service(service_name: str) -> (bool, str):
    """Executes the restart script for a given service."""
    script_path = f"scripts/restart_{service_name}.py"
    try:
        result = subprocess.run(["python", script_path], capture_output=True, text=True, check=True)
        return True, result.stdout
    except FileNotFoundError:
        return False, f"Error: Script for service '{service_name}' not found."
    except subprocess.CalledProcessError as e:
        return False, f"Error executing script for '{service_name}': {e.stderr}"
