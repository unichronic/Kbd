from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class IncidentEvent(BaseModel):
    """Standardized incident event schema"""
    id: str = Field(..., description="Unique incident identifier")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the incident was detected")
    status: str = Field(..., description="Incident status: new, triaged, resolved")
    severity: str = Field(..., description="Severity level: low, medium, high, critical")
    source: str = Field(..., description="Source system: prometheus, loki, github, etc.")
    title: str = Field(..., description="Incident title")
    description: str = Field(..., description="Detailed incident description")
    affected_service: Optional[str] = Field(None, description="Affected service name")
    affected_namespace: Optional[str] = Field(None, description="Affected Kubernetes namespace")
    labels: Dict[str, str] = Field(default_factory=dict, description="Additional labels and metadata")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Raw data from source system")
    
    # AI Analysis fields (added by Planner)
    ai_hypothesis: Optional[str] = Field(None, description="AI-generated root cause hypothesis")
    confidence_score: Optional[float] = Field(None, description="Confidence score for AI analysis")
    
    # Resolution fields (added by Actor)
    resolution_action: Optional[str] = Field(None, description="Action taken to resolve the incident")
    resolution_timestamp: Optional[datetime] = Field(None, description="When the incident was resolved")
    resolution_notes: Optional[str] = Field(None, description="Notes about the resolution")


class PlanEvent(BaseModel):
    """Standardized remediation plan event schema"""
    id: str = Field(..., description="Unique plan identifier")
    incident_id: str = Field(..., description="Associated incident ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the plan was created")
    status: str = Field(..., description="Plan status: proposed, approved, executing, completed, failed")
    risk_level: str = Field(..., description="Risk level: low, medium, high")
    title: str = Field(..., description="Plan title")
    description: str = Field(..., description="Plan description")
    steps: list = Field(default_factory=list, description="List of execution steps")
    estimated_duration: int = Field(..., description="Estimated duration in seconds")
    requires_approval: bool = Field(True, description="Whether the plan requires manual approval")
    
    # Approval fields (added by Collaborator)
    approved_by: Optional[str] = Field(None, description="Who approved the plan")
    approval_timestamp: Optional[datetime] = Field(None, description="When the plan was approved")
    approval_notes: Optional[str] = Field(None, description="Approval notes")
    
    # Execution fields (added by Actor)
    executed_by: Optional[str] = Field(None, description="Who executed the plan")
    execution_started: Optional[datetime] = Field(None, description="When execution started")
    execution_completed: Optional[datetime] = Field(None, description="When execution completed")
    execution_logs: list = Field(default_factory=list, description="Execution logs")
    execution_results: list = Field(default_factory=list, description="Step execution results")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class PlanStep(BaseModel):
    """Individual step within a remediation plan"""
    step_id: str = Field(..., description="Unique step identifier")
    description: str = Field(..., description="Step description")
    action_type: str = Field(..., description="Action type: kubectl, aws, custom")
    command: str = Field(..., description="Command to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    expected_duration: int = Field(..., description="Expected duration in seconds")
    rollback_command: Optional[str] = Field(None, description="Rollback command if step fails")
    requires_confirmation: bool = Field(False, description="Whether step requires manual confirmation")


