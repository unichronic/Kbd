"""
Quota Management for Gemini API

This module provides utilities to monitor and manage API quota usage
to avoid hitting rate limits and conserve API calls.
"""

import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class QuotaManager:
    """Manages API quota usage and provides intelligent request prioritization."""
    
    def __init__(self, daily_limit: int = 50, hourly_limit: int = 10):
        self.daily_limit = daily_limit
        self.hourly_limit = hourly_limit
        self.daily_usage: List[float] = []
        self.hourly_usage: List[float] = []
        self.request_history: List[Dict] = []
    
    def can_make_request(self, priority: str = "normal") -> bool:
        """
        Check if we can make a request based on current quota usage.
        
        Args:
            priority: Request priority ("high", "normal", "low")
            
        Returns:
            True if request can be made, False otherwise
        """
        current_time = time.time()
        
        # Clean old usage data
        self._clean_old_usage(current_time)
        
        # Check daily limit
        if len(self.daily_usage) >= self.daily_limit:
            return False
        
        # Check hourly limit
        if len(self.hourly_usage) >= self.hourly_limit:
            return False
        
        # For low priority requests, be more conservative
        if priority == "low" and len(self.daily_usage) > self.daily_limit * 0.8:
            return False
        
        return True
    
    def record_request(self, request_type: str, priority: str = "normal", success: bool = True):
        """
        Record a request to track quota usage.
        
        Args:
            request_type: Type of request (e.g., "plan_generation", "context_gathering")
            priority: Request priority
            success: Whether the request was successful
        """
        current_time = time.time()
        
        self.daily_usage.append(current_time)
        self.hourly_usage.append(current_time)
        
        self.request_history.append({
            "timestamp": current_time,
            "type": request_type,
            "priority": priority,
            "success": success
        })
    
    def get_quota_status(self) -> Dict:
        """Get current quota usage status."""
        current_time = time.time()
        self._clean_old_usage(current_time)
        
        return {
            "daily_usage": len(self.daily_usage),
            "daily_limit": self.daily_limit,
            "daily_remaining": self.daily_limit - len(self.daily_usage),
            "hourly_usage": len(self.hourly_usage),
            "hourly_limit": self.hourly_limit,
            "hourly_remaining": self.hourly_limit - len(self.hourly_usage),
            "usage_percentage": (len(self.daily_usage) / self.daily_limit) * 100,
            "can_make_request": self.can_make_request(),
            "estimated_reset_time": self._get_reset_time()
        }
    
    def get_recommendations(self) -> List[str]:
        """Get recommendations for quota management."""
        status = self.get_quota_status()
        recommendations = []
        
        if status["usage_percentage"] > 80:
            recommendations.append("⚠️ High quota usage - consider using basic planning for low-priority incidents")
        
        if status["usage_percentage"] > 90:
            recommendations.append("🚨 Critical quota usage - switch to basic planning only")
        
        if status["hourly_usage"] > self.hourly_limit * 0.8:
            recommendations.append("⏰ High hourly usage - consider rate limiting")
        
        if not status["can_make_request"]:
            recommendations.append("❌ Quota exceeded - wait for reset or upgrade plan")
        
        if not recommendations:
            recommendations.append("✅ Quota usage is healthy")
        
        return recommendations
    
    def _clean_old_usage(self, current_time: float):
        """Remove old usage data outside the time windows."""
        # Remove usage older than 24 hours
        self.daily_usage = [t for t in self.daily_usage if current_time - t < 86400]
        
        # Remove usage older than 1 hour
        self.hourly_usage = [t for t in self.hourly_usage if current_time - t < 3600]
    
    def _get_reset_time(self) -> Optional[str]:
        """Get estimated time when quota will reset."""
        if not self.daily_usage:
            return None
        
        oldest_usage = min(self.daily_usage)
        reset_time = oldest_usage + 86400  # 24 hours later
        
        if reset_time > time.time():
            return datetime.fromtimestamp(reset_time).strftime("%Y-%m-%d %H:%M:%S")
        
        return "Available now"


# Global quota manager instance
quota_manager = QuotaManager()


def should_use_enhanced_planning_with_quota(incident_data: Dict, priority: str = "normal") -> bool:
    """
    Determine if enhanced planning should be used based on both incident priority and quota availability.
    
    Args:
        incident_data: Incident data to analyze
        priority: Request priority
        
    Returns:
        True if enhanced planning should be used
    """
    # Check quota first
    if not quota_manager.can_make_request(priority):
        return False
    
    # Then check incident characteristics
    severity = incident_data.get('derived', {}).get('severity', 'low')
    error_log_count = incident_data.get('derived', {}).get('error_log_count', 0)
    service = incident_data.get('affected_service', '')
    
    # Always use enhanced planning for high-severity incidents if quota allows
    if severity == 'high':
        return True
    
    # Use enhanced planning for critical services
    critical_services = ['user-service', 'payment-service', 'auth-service', 'api-gateway']
    if any(critical in service.lower() for critical in critical_services):
        return True
    
    # Use enhanced planning if there are many error logs (complex incident)
    if error_log_count > 3:
        return True
    
    # For low-severity, simple incidents, use basic planning to conserve quota
    return False


def record_planning_request(request_type: str, priority: str = "normal", success: bool = True):
    """Record a planning request for quota tracking."""
    quota_manager.record_request(request_type, priority, success)


def get_quota_status() -> Dict:
    """Get current quota status."""
    return quota_manager.get_quota_status()


def get_quota_recommendations() -> List[str]:
    """Get quota management recommendations."""
    return quota_manager.get_recommendations()
