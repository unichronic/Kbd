"""
Structured prompt templates for the Planner Agent.

This module provides comprehensive prompt templates for different
types of incident analysis and plan generation.
"""

from typing import Any, Dict, List
from langchain.prompts import PromptTemplate


class PromptTemplates:
    """Collection of prompt templates for incident analysis."""
    
    @staticmethod
    def get_comprehensive_analysis_template() -> PromptTemplate:
        """Get the main comprehensive analysis prompt template."""
        template = """
You are an expert Site Reliability Engineer (SRE) analyzing a Kubernetes incident. 
Your task is to provide a comprehensive root cause analysis and remediation plan.

**INCIDENT DETAILS:**
- Service: {service}
- Title: {title}
- Summary: {summary}
- Severity: {severity}
- Incident ID: {incident_id}

**REAL-TIME CONTEXT:**
- Recent Logs: {loki_logs}
- Kubernetes Events: {k8s_events}
- System Metrics: {metrics}

**HISTORICAL CONTEXT:**
- Similar Past Incidents: {similar_incidents}
- Recent Code Changes: {recent_commits}

**EXTERNAL KNOWLEDGE:**
- Public Documentation & Solutions: {web_knowledge}

**ANALYSIS REQUIREMENTS:**
1. **Root Cause Analysis**: Identify the most likely cause based on all available context
2. **Impact Assessment**: Evaluate the severity and scope of the incident
3. **Remediation Plan**: Provide step-by-step actions to resolve the issue
4. **Risk Assessment**: Rate the risk level (1-5 scale)
5. **Verification Steps**: How to confirm the resolution
6. **Rollback Plan**: How to revert changes if needed

**OUTPUT FORMAT:**
Return ONLY valid JSON with the following structure:
{{
    "root_cause": "Detailed analysis of what's happening and why",
    "impact_assessment": "Description of the impact and scope",
    "remediation_plan": [
        {{
            "step": 1,
            "action": "Description of the action",
            "target": "What component/service to target",
            "command": "Specific command or action to take",
            "notes": "Additional context or warnings",
            "estimated_time": "Estimated time to complete"
        }}
    ],
    "risk_score": 3,
    "verification_steps": [
        "Step 1: Check service health",
        "Step 2: Verify metrics are normal"
    ],
    "rollback_plan": [
        "Step 1: Revert configuration changes",
        "Step 2: Restart affected services"
    ],
    "prevention_recommendations": [
        "Recommendation 1: Add monitoring",
        "Recommendation 2: Update documentation"
    ]
}}

**IMPORTANT GUIDELINES:**
- Prefer reversible actions first
- Include pre-checks and post-verification
- Keep commands short and safe
- Consider the service context and dependencies
- Base recommendations on the historical context when available
- Return ONLY valid JSON, no markdown formatting
"""
        return PromptTemplate.from_template(template)
    
    @staticmethod
    def get_quick_analysis_template() -> PromptTemplate:
        """Get a quick analysis template for urgent incidents."""
        template = """
You are an SRE responding to an urgent Kubernetes incident. Provide a quick but thorough analysis.

**INCIDENT:**
- Service: {service}
- Title: {title}
- Severity: {severity}

**KEY CONTEXT:**
- Error Logs: {error_logs}
- Recent Changes: {recent_changes}

**QUICK ANALYSIS REQUIRED:**
Provide immediate actions to stabilize the service and prevent further impact.

Return JSON with:
{{
    "immediate_actions": [
        {{
            "action": "Quick action description",
            "command": "Specific command",
            "priority": "high|medium|low"
        }}
    ],
    "root_cause_hypothesis": "Most likely cause",
    "risk_score": 4,
    "next_steps": ["Follow-up action 1", "Follow-up action 2"]
}}
"""
        return PromptTemplate.from_template(template)
    
    @staticmethod
    def get_deep_dive_template() -> PromptTemplate:
        """Get a deep dive analysis template for complex incidents."""
        template = """
You are conducting a deep dive analysis of a complex Kubernetes incident. 
This requires thorough investigation and comprehensive planning.

**INCIDENT OVERVIEW:**
- Service: {service}
- Title: {title}
- Duration: {duration}
- Affected Components: {affected_components}

**COMPREHENSIVE CONTEXT:**
- Full Log Analysis: {detailed_logs}
- Historical Patterns: {historical_patterns}
- Infrastructure Changes: {infrastructure_changes}
- Performance Metrics: {performance_metrics}
- External Dependencies: {external_dependencies}

**DEEP DIVE ANALYSIS:**
1. **Timeline Analysis**: When did the issue start and how did it evolve?
2. **Dependency Analysis**: What components are affected and how?
3. **Pattern Recognition**: Are there recurring patterns in the data?
4. **Root Cause Investigation**: Multiple hypothesis testing
5. **Impact Modeling**: What could happen if not resolved?
6. **Long-term Solutions**: Beyond immediate fixes

**OUTPUT FORMAT:**
Return comprehensive JSON with:
{{
    "timeline_analysis": {{
        "incident_start": "Estimated start time",
        "escalation_points": ["Key escalation moments"],
        "current_state": "Current situation"
    }},
    "dependency_analysis": {{
        "affected_services": ["Service 1", "Service 2"],
        "critical_path": "Critical dependency chain",
        "bottlenecks": ["Identified bottlenecks"]
    }},
    "root_cause_hypotheses": [
        {{
            "hypothesis": "Most likely cause",
            "confidence": 0.8,
            "evidence": ["Supporting evidence"],
            "test_actions": ["How to test this hypothesis"]
        }}
    ],
    "comprehensive_plan": {{
        "immediate_stabilization": ["Immediate actions"],
        "investigation_phase": ["Investigation steps"],
        "resolution_phase": ["Resolution actions"],
        "validation_phase": ["Validation steps"],
        "prevention_phase": ["Prevention measures"]
    }},
    "risk_assessment": {{
        "current_risk": 4,
        "potential_escalation": "How it could get worse",
        "business_impact": "Impact on business operations"
    }}
}}
"""
        return PromptTemplate.from_template(template)
    
    @staticmethod
    def get_learning_template() -> PromptTemplate:
        """Get a template for learning from incident resolution."""
        template = """
You are analyzing a resolved incident to extract learnings and improve future responses.

**INCIDENT SUMMARY:**
- Service: {service}
- Resolution: {resolution}
- Time to Resolution: {ttr}
- Actions Taken: {actions_taken}

**POST-INCIDENT ANALYSIS:**
1. **What Worked Well**: What actions were effective?
2. **What Could Be Improved**: What could have been done better?
3. **Knowledge Gaps**: What information was missing?
4. **Process Improvements**: How can the process be improved?
5. **Prevention Measures**: How can similar incidents be prevented?

Return JSON with:
{{
    "lessons_learned": {{
        "effective_actions": ["What worked well"],
        "improvement_areas": ["What could be better"],
        "knowledge_gaps": ["Missing information"],
        "process_improvements": ["Process suggestions"]
    }},
    "prevention_recommendations": [
        {{
            "recommendation": "Specific recommendation",
            "priority": "high|medium|low",
            "implementation_effort": "low|medium|high"
        }}
    ],
    "documentation_updates": [
        "Documentation item 1",
        "Documentation item 2"
    ]
}}
"""
        return PromptTemplate.from_template(template)
    
    @staticmethod
    def format_context_for_prompt(context_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Format context data for use in prompts.
        
        Args:
            context_data: Raw context data from various sources
            
        Returns:
            Formatted context strings for prompts
        """
        formatted = {}
        
        # Format Loki logs
        loki_logs = context_data.get('loki_logs', [])
        if loki_logs:
            formatted['loki_logs'] = "\n".join([
                f"[{log.get('timestamp', 'unknown')}] {log.get('level', 'info').upper()}: {log.get('message', '')}"
                for log in loki_logs[:20]  # Limit to first 20 logs
            ])
        else:
            formatted['loki_logs'] = "No recent logs available"
        
        # Format similar incidents
        similar_incidents = context_data.get('similar_incidents', [])
        if similar_incidents:
            formatted['similar_incidents'] = "\n".join([
                f"- {incident.title} (Similarity: {incident.similarity_score:.2f}): {incident.summary}"
                for incident in similar_incidents
            ])
        else:
            formatted['similar_incidents'] = "No similar incidents found"
        
        # Format recent commits
        recent_commits = context_data.get('recent_commits', [])
        if recent_commits:
            formatted['recent_commits'] = "\n".join([
                f"- {commit.get('sha', 'unknown')[:8]}: {commit.get('message', '')} (by {commit.get('author', 'unknown')})"
                for commit in recent_commits[:10]  # Limit to first 10 commits
            ])
        else:
            formatted['recent_commits'] = "No recent commits found"
        
        # Format web knowledge
        web_knowledge = context_data.get('web_knowledge', [])
        if web_knowledge:
            formatted['web_knowledge'] = "\n".join([
                f"- {result.get('title', '')}: {result.get('content', '')[:200]}..."
                for result in web_knowledge[:5]  # Limit to first 5 results
            ])
        else:
            formatted['web_knowledge'] = "No relevant external knowledge found"
        
        return formatted
