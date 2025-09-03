"""
Enhanced AI reasoning core for the Planner Agent.

This module provides the main AI reasoning capabilities using LangChain
and Google Gemini for comprehensive incident analysis and plan generation.
"""

import json
import re
from typing import Any, Dict, List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
from .prompt_templates import PromptTemplates
from ..models.context import EnrichedContext


class PlannerEngine:
    """Enhanced AI reasoning engine for incident analysis and plan generation."""
    
    def __init__(
        self,
        model_name: str = "gemini-1.5-flash",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None
    ):
        """
        Initialize the planner engine.
        
        Args:
            model_name: Name of the Gemini model to use
            temperature: Temperature for response generation
            max_tokens: Maximum tokens in response
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Initialize the LLM
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_output_tokens=max_tokens
        )
        
        # Initialize prompt templates
        self.prompt_templates = PromptTemplates()
    
    async def generate_comprehensive_plan(
        self, 
        incident_data: Dict[str, Any], 
        enriched_context: EnrichedContext
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive remediation plan using all available context.
        
        Args:
            incident_data: Normalized incident data
            enriched_context: Enriched context from all sources
            
        Returns:
            Comprehensive remediation plan
        """
        try:
            # Get the comprehensive analysis template
            prompt_template = self.prompt_templates.get_comprehensive_analysis_template()
            
            # Format context data for the prompt
            formatted_context = self.prompt_templates.format_context_for_prompt({
                'loki_logs': enriched_context.loki_logs,
                'similar_incidents': enriched_context.similar_incidents,
                'recent_commits': enriched_context.recent_commits,
                'web_knowledge': enriched_context.web_knowledge
            })
            
            # Prepare prompt variables
            prompt_vars = {
                'service': incident_data.get('affected_service', 'unknown'),
                'title': incident_data.get('title', 'Unknown Incident'),
                'summary': incident_data.get('hypothesis', 'No summary available'),
                'severity': incident_data.get('derived', {}).get('severity', 'unknown'),
                'incident_id': incident_data.get('id', 'unknown'),
                'loki_logs': formatted_context['loki_logs'],
                'k8s_events': self._format_k8s_events(incident_data.get('k8s_events', [])),
                'metrics': self._format_metrics(incident_data.get('metrics_summary', {})),
                'similar_incidents': formatted_context['similar_incidents'],
                'recent_commits': formatted_context['recent_commits'],
                'web_knowledge': formatted_context['web_knowledge']
            }
            
            # Format the prompt
            formatted_prompt = prompt_template.format(**prompt_vars)
            
            # Generate response
            response = await self.llm.ainvoke([HumanMessage(content=formatted_prompt)])
            
            # Parse the response
            plan = self._parse_llm_response(response.content)
            
            # Add metadata
            plan['metadata'] = {
                'model_used': self.model_name,
                'context_sources': [source.value for source in enriched_context.sources_used],
                'gathering_time_ms': enriched_context.gathering_time_ms,
                'context_errors': enriched_context.gathering_errors
            }
            
            print(f"PlannerEngine: Generated comprehensive plan using {len(enriched_context.sources_used)} context sources")
            return plan
            
        except Exception as e:
            print(f"PlannerEngine: Error generating comprehensive plan: {e}")
            return self._create_fallback_plan(incident_data, str(e))
    
    async def generate_quick_plan(
        self, 
        incident_data: Dict[str, Any], 
        enriched_context: EnrichedContext
    ) -> Dict[str, Any]:
        """
        Generate a quick plan for urgent incidents.
        
        Args:
            incident_data: Normalized incident data
            enriched_context: Enriched context from all sources
            
        Returns:
            Quick remediation plan
        """
        try:
            # Get the quick analysis template
            prompt_template = self.prompt_templates.get_quick_analysis_template()
            
            # Extract error logs
            error_logs = [
                log for log in enriched_context.loki_logs 
                if log.get('level') == 'error'
            ][:5]  # Limit to first 5 error logs
            
            # Extract recent changes
            recent_changes = enriched_context.recent_commits[:3]  # Limit to first 3 commits
            
            # Prepare prompt variables
            prompt_vars = {
                'service': incident_data.get('affected_service', 'unknown'),
                'title': incident_data.get('title', 'Unknown Incident'),
                'severity': incident_data.get('derived', {}).get('severity', 'unknown'),
                'error_logs': "\n".join([log.get('message', '') for log in error_logs]),
                'recent_changes': "\n".join([commit.get('message', '') for commit in recent_changes])
            }
            
            # Format the prompt
            formatted_prompt = prompt_template.format(**prompt_vars)
            
            # Generate response
            response = await self.llm.ainvoke([HumanMessage(content=formatted_prompt)])
            
            # Parse the response
            plan = self._parse_llm_response(response.content)
            
            # Add metadata
            plan['metadata'] = {
                'plan_type': 'quick',
                'model_used': self.model_name,
                'context_sources': [source.value for source in enriched_context.sources_used]
            }
            
            print(f"PlannerEngine: Generated quick plan for urgent incident")
            return plan
            
        except Exception as e:
            print(f"PlannerEngine: Error generating quick plan: {e}")
            return self._create_fallback_plan(incident_data, str(e))
    
    async def generate_deep_dive_plan(
        self, 
        incident_data: Dict[str, Any], 
        enriched_context: EnrichedContext
    ) -> Dict[str, Any]:
        """
        Generate a deep dive analysis for complex incidents.
        
        Args:
            incident_data: Normalized incident data
            enriched_context: Enriched context from all sources
            
        Returns:
            Deep dive analysis and plan
        """
        try:
            # Get the deep dive template
            prompt_template = self.prompt_templates.get_deep_dive_template()
            
            # Prepare comprehensive context
            prompt_vars = {
                'service': incident_data.get('affected_service', 'unknown'),
                'title': incident_data.get('title', 'Unknown Incident'),
                'duration': 'Unknown',  # Could be calculated from timestamps
                'affected_components': self._identify_affected_components(incident_data),
                'detailed_logs': self._format_detailed_logs(enriched_context.loki_logs),
                'historical_patterns': self._analyze_historical_patterns(enriched_context.similar_incidents),
                'infrastructure_changes': self._format_infrastructure_changes(enriched_context.recent_commits),
                'performance_metrics': self._format_metrics(incident_data.get('metrics_summary', {})),
                'external_dependencies': self._identify_external_dependencies(incident_data)
            }
            
            # Format the prompt
            formatted_prompt = prompt_template.format(**prompt_vars)
            
            # Generate response
            response = await self.llm.ainvoke([HumanMessage(content=formatted_prompt)])
            
            # Parse the response
            plan = self._parse_llm_response(response.content)
            
            # Add metadata
            plan['metadata'] = {
                'plan_type': 'deep_dive',
                'model_used': self.model_name,
                'context_sources': [source.value for source in enriched_context.sources_used],
                'analysis_depth': 'comprehensive'
            }
            
            print(f"PlannerEngine: Generated deep dive analysis")
            return plan
            
        except Exception as e:
            print(f"PlannerEngine: Error generating deep dive plan: {e}")
            return self._create_fallback_plan(incident_data, str(e))
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse LLM response and extract JSON.
        
        Args:
            response_text: Raw response from LLM
            
        Returns:
            Parsed JSON response
        """
        try:
            # Clean the response text
            cleaned = response_text.strip()
            
            # Remove markdown code fences if present
            if cleaned.startswith("```"):
                lines = cleaned.split('\n')
                # Find the JSON content between code fences
                json_lines = []
                in_json = False
                for line in lines:
                    if line.strip().startswith("```"):
                        in_json = not in_json
                    elif in_json:
                        json_lines.append(line)
                cleaned = '\n'.join(json_lines)
            
            # Try to parse as JSON
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                # Try to extract JSON from the text
                json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
                else:
                    raise ValueError("No valid JSON found in response")
                    
        except Exception as e:
            print(f"PlannerEngine: Error parsing LLM response: {e}")
            raise ValueError(f"Failed to parse LLM response: {e}")
    
    def _create_fallback_plan(self, incident_data: Dict[str, Any], error: str) -> Dict[str, Any]:
        """Create a fallback plan when LLM generation fails."""
        return {
            "root_cause": "Unable to determine root cause due to analysis error",
            "impact_assessment": "Impact assessment unavailable",
            "remediation_plan": [
                {
                    "step": 1,
                    "action": "Check service health",
                    "target": incident_data.get('affected_service', 'unknown'),
                    "command": "kubectl get pods -l app=" + incident_data.get('affected_service', 'unknown'),
                    "notes": "Basic health check",
                    "estimated_time": "1 minute"
                },
                {
                    "step": 2,
                    "action": "Review logs",
                    "target": incident_data.get('affected_service', 'unknown'),
                    "command": "kubectl logs -l app=" + incident_data.get('affected_service', 'unknown'),
                    "notes": "Check for error messages",
                    "estimated_time": "2 minutes"
                }
            ],
            "risk_score": 3,
            "verification_steps": [
                "Check if service is responding",
                "Verify error rate is decreasing"
            ],
            "rollback_plan": [
                "Restart the affected service",
                "Check for recent deployments to rollback"
            ],
            "prevention_recommendations": [
                "Add more comprehensive monitoring",
                "Improve error handling and logging"
            ],
            "metadata": {
                "plan_type": "fallback",
                "error": error,
                "fallback_reason": "LLM generation failed"
            }
        }
    
    def _format_k8s_events(self, k8s_events: List[Dict[str, Any]]) -> str:
        """Format Kubernetes events for the prompt."""
        if not k8s_events:
            return "No Kubernetes events available"
        
        formatted_events = []
        for event in k8s_events[:10]:  # Limit to first 10 events
            formatted_events.append(
                f"- {event.get('type', 'Unknown')}: {event.get('reason', 'Unknown')} - {event.get('message', '')}"
            )
        
        return "\n".join(formatted_events)
    
    def _format_metrics(self, metrics: Dict[str, Any]) -> str:
        """Format metrics for the prompt."""
        if not metrics:
            return "No metrics available"
        
        formatted_metrics = []
        for key, value in metrics.items():
            if value is not None:
                formatted_metrics.append(f"- {key}: {value}")
        
        return "\n".join(formatted_metrics)
    
    def _identify_affected_components(self, incident_data: Dict[str, Any]) -> str:
        """Identify affected components from incident data."""
        components = [incident_data.get('affected_service', 'unknown')]
        
        # Add components from logs
        if incident_data.get('logs'):
            for log in incident_data['logs'][:5]:
                if isinstance(log, dict) and log.get('pod'):
                    components.append(log['pod'])
        
        return ", ".join(set(components))
    
    def _format_detailed_logs(self, logs: List[Dict[str, Any]]) -> str:
        """Format detailed logs for deep dive analysis."""
        if not logs:
            return "No detailed logs available"
        
        formatted_logs = []
        for log in logs[:50]:  # Limit to first 50 logs
            timestamp = log.get('timestamp', 'unknown')
            level = log.get('level', 'info')
            message = log.get('message', '')
            source = log.get('source', 'unknown')
            
            formatted_logs.append(f"[{timestamp}] {level.upper()} ({source}): {message}")
        
        return "\n".join(formatted_logs)
    
    def _analyze_historical_patterns(self, similar_incidents: List[Any]) -> str:
        """Analyze patterns from similar incidents."""
        if not similar_incidents:
            return "No historical patterns available"
        
        patterns = []
        for incident in similar_incidents:
            if hasattr(incident, 'resolution') and incident.resolution:
                patterns.append(f"- {incident.title}: {incident.resolution}")
        
        return "\n".join(patterns) if patterns else "No resolution patterns found"
    
    def _format_infrastructure_changes(self, commits: List[Dict[str, Any]]) -> str:
        """Format infrastructure changes from commits."""
        if not commits:
            return "No infrastructure changes found"
        
        infrastructure_commits = []
        for commit in commits:
            message = commit.get('message', '').lower()
            if any(keyword in message for keyword in ['deploy', 'config', 'infrastructure', 'k8s', 'helm']):
                infrastructure_commits.append(f"- {commit.get('message', '')}")
        
        return "\n".join(infrastructure_commits) if infrastructure_commits else "No infrastructure changes found"
    
    def _identify_external_dependencies(self, incident_data: Dict[str, Any]) -> str:
        """Identify external dependencies from incident data."""
        # This is a simplified implementation
        # In a real system, you might analyze logs for external service calls
        return "External dependencies analysis not available"
