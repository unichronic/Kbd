"""
Loki client for fetching real-time logs.

This module provides integration with Grafana Loki for retrieving
recent logs related to incidents.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
import httpx
from ..models.context import ContextSource


class LokiClient:
    """Client for interacting with Grafana Loki."""
    
    def __init__(self, base_url: str = "http://localhost:3100", timeout: int = 10):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def get_recent_logs(self, service_name: str, hours_back: int = 2) -> List[Dict[str, Any]]:
        """
        Fetch recent logs for a service from Loki.
        
        Args:
            service_name: Name of the service to fetch logs for
            hours_back: How many hours back to look for logs
            
        Returns:
            List of log entries
        """
        try:
            # Build Loki query for the service
            query = f'{{service="{service_name}"}}'
            
            # Calculate time range
            end_time = int(asyncio.get_event_loop().time() * 1000)  # Current time in ms
            start_time = end_time - (hours_back * 60 * 60 * 1000)  # hours_back in ms
            
            # Query Loki API
            params = {
                'query': query,
                'start': start_time,
                'end': end_time,
                'limit': 1000
            }
            
            response = await self.client.get(
                f"{self.base_url}/loki/api/v1/query_range",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            logs = []
            
            # Parse Loki response format
            if 'data' in data and 'result' in data['data']:
                for stream in data['data']['result']:
                    if 'values' in stream:
                        for timestamp, message in stream['values']:
                            log_entry = {
                                'timestamp': timestamp,
                                'message': message,
                                'source': 'loki',
                                'labels': stream.get('stream', {})
                            }
                            logs.append(log_entry)
            
            print(f"Loki: Retrieved {len(logs)} log entries for service {service_name}")
            return logs
            
        except Exception as e:
            print(f"Loki: Error fetching logs for {service_name}: {e}")
            return []
    
    async def search_error_logs(self, service_name: str, hours_back: int = 2) -> List[Dict[str, Any]]:
        """
        Search specifically for error logs in a service.
        
        Args:
            service_name: Name of the service
            hours_back: How many hours back to look
            
        Returns:
            List of error log entries
        """
        try:
            # Build query for error logs
            query = f'{{service="{service_name}"}} |= "error" |= "exception" |= "panic"'
            
            end_time = int(asyncio.get_event_loop().time() * 1000)
            start_time = end_time - (hours_back * 60 * 60 * 1000)
            
            params = {
                'query': query,
                'start': start_time,
                'end': end_time,
                'limit': 500
            }
            
            response = await self.client.get(
                f"{self.base_url}/loki/api/v1/query_range",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            error_logs = []
            
            if 'data' in data and 'result' in data['data']:
                for stream in data['data']['result']:
                    if 'values' in stream:
                        for timestamp, message in stream['values']:
                            log_entry = {
                                'timestamp': timestamp,
                                'message': message,
                                'source': 'loki',
                                'level': 'error',
                                'labels': stream.get('stream', {})
                            }
                            error_logs.append(log_entry)
            
            print(f"Loki: Retrieved {len(error_logs)} error log entries for service {service_name}")
            return error_logs
            
        except Exception as e:
            print(f"Loki: Error fetching error logs for {service_name}: {e}")
            return []
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
