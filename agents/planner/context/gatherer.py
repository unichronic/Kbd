"""
Context enrichment pipeline orchestrator.

This module coordinates context gathering from multiple sources
and provides a unified interface for enriched incident context.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
from .loki_client import LokiClient
from .chromadb_client import ChromaDBClient
from .github_client import GitHubClient
from .web_search_client import WebSearchClient
from models.context import EnrichedContext, ContextSource


class ContextGatherer:
    """Orchestrates context gathering from multiple sources."""
    
    def __init__(
        self,
        loki_url: str = "http://localhost:3100",
        chromadb_host: str = "localhost",
        chromadb_port: int = 8002,
        github_token: Optional[str] = None,
        github_repo_owner: Optional[str] = None,
        github_repo_name: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        chromadb_collection: str = "incident_history",
        chromadb_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        """Initialize context gatherer with all client configurations."""
        
        # Initialize clients
        self.loki_client = LokiClient(base_url=loki_url)
        self.chromadb_client = ChromaDBClient(
            host=chromadb_host,
            port=chromadb_port,
            collection_name=chromadb_collection,
            embedding_model=chromadb_embedding_model
        )
        self.github_client = GitHubClient(
            token=github_token,
            repo_owner=github_repo_owner,
            repo_name=github_repo_name
        )
        self.web_search_client = WebSearchClient(api_key=tavily_api_key)
    
    async def gather_all_context(
        self, 
        incident_data: Dict[str, Any],
        parallel: bool = True,
        confidence_threshold: float = 0.8
    ) -> EnrichedContext:
        """
        Gather context from all available sources with intelligent web search.
        
        Args:
            incident_data: Current incident data
            parallel: Whether to gather context in parallel or sequentially
            confidence_threshold: Threshold for triggering web search (0.0-1.0)
            
        Returns:
            EnrichedContext with all gathered information
        """
        start_time = time.time()
        enriched_context = EnrichedContext()
        
        service_name = incident_data.get("affected_service", "unknown")
        
        # Step 1: Always gather internal context first (Loki, ChromaDB, GitHub)
        if parallel:
            # Gather internal context in parallel
            internal_tasks = [
                self._gather_loki_context(service_name),
                self._gather_chromadb_context(incident_data),
                self._gather_github_context(service_name)
            ]
            
            internal_results = await asyncio.gather(*internal_tasks, return_exceptions=True)
            
            # Process internal results
            enriched_context.loki_logs = internal_results[0] if not isinstance(internal_results[0], Exception) else []
            chromadb_result = internal_results[1] if not isinstance(internal_results[1], Exception) else ([], 0.0)
            enriched_context.recent_commits = internal_results[2] if not isinstance(internal_results[2], Exception) else []
            
            # Track internal errors
            for i, result in enumerate(internal_results):
                if isinstance(result, Exception):
                    source = [ContextSource.LOKI, ContextSource.CHROMADB, ContextSource.GITHUB][i]
                    enriched_context.gathering_errors[source] = str(result)
        
        else:
            # Gather internal context sequentially
            enriched_context.loki_logs = await self._gather_loki_context(service_name)
            chromadb_result = await self._gather_chromadb_context(incident_data)
            enriched_context.recent_commits = await self._gather_github_context(service_name)
        
        # Extract ChromaDB results and confidence
        if isinstance(chromadb_result, tuple):
            enriched_context.similar_incidents, internal_confidence = chromadb_result
        else:
            enriched_context.similar_incidents = chromadb_result
            internal_confidence = 0.0
        
        enriched_context.internal_confidence = internal_confidence
        
        # Step 2: Evaluate confidence and decide on web search
        print(f"ContextGatherer: Evaluating web search decision...")
        print(f"ContextGatherer: Internal confidence: {internal_confidence:.3f}")
        print(f"ContextGatherer: Confidence threshold: {confidence_threshold}")
        print(f"ContextGatherer: Similar incidents found: {len(enriched_context.similar_incidents)}")
        
        should_search_web = self._should_trigger_web_search(
            internal_confidence, 
            confidence_threshold, 
            enriched_context.similar_incidents
        )
        
        enriched_context.web_search_triggered = should_search_web
        
        if should_search_web:
            # Step 3: Trigger web search only if confidence is low
            print(f"ContextGatherer: Decision: Trigger web search (confidence too low)")
            try:
                enriched_context.web_knowledge = await self._gather_web_search_context(incident_data)
                enriched_context.sources_used.append(ContextSource.WEB_SEARCH)
                enriched_context.web_search_reason = f"Low internal confidence ({internal_confidence:.3f} < {confidence_threshold})"
                print(f"ContextGatherer: Web search completed successfully")
            except Exception as e:
                enriched_context.gathering_errors[ContextSource.WEB_SEARCH] = str(e)
                enriched_context.web_search_reason = f"Web search failed: {e}"
                print(f"ContextGatherer: Web search failed: {e}")
        else:
            enriched_context.web_knowledge = []
            enriched_context.web_search_reason = f"High internal confidence ({internal_confidence:.3f} >= {confidence_threshold})"
            print(f"ContextGatherer: Decision: Skip web search (confidence sufficient)")
        
        # Calculate gathering time
        enriched_context.gathering_time_ms = int((time.time() - start_time) * 1000)
        
        # Track which sources were used
        enriched_context.sources_used.extend([
            ContextSource.LOKI,
            ContextSource.CHROMADB,
            ContextSource.GITHUB
        ])
        
        print(f"ContextGatherer: Gathered context in {enriched_context.gathering_time_ms}ms (confidence: {internal_confidence:.3f})")
        return enriched_context
    
    async def _gather_loki_context(self, service_name: str) -> List[Dict[str, Any]]:
        """Gather context from Loki logs."""
        try:
            print(f"ContextGatherer: Gathering Loki context for service: {service_name}")
            
            # Get both recent logs and error logs
            print(f"ContextGatherer: Fetching recent logs from Loki...")
            recent_logs = await self.loki_client.get_recent_logs(service_name, hours_back=2)
            print(f"ContextGatherer: Found {len(recent_logs)} recent log entries")
            
            print(f"ContextGatherer: Searching for error logs in Loki...")
            error_logs = await self.loki_client.search_error_logs(service_name, hours_back=2)
            print(f"ContextGatherer: Found {len(error_logs)} error log entries")
            
            # Combine and deduplicate
            all_logs = recent_logs + error_logs
            unique_logs = self._deduplicate_logs(all_logs)
            print(f"ContextGatherer: Deduplicated to {len(unique_logs)} unique log entries")
            
            return unique_logs
            
        except Exception as e:
            print(f"ContextGatherer: Error gathering Loki context: {e}")
            print(f"ContextGatherer: Loki error type: {type(e).__name__}")
            return []
    
    async def _gather_chromadb_context(self, incident_data: Dict[str, Any]) -> tuple[List[Any], float]:
        """Gather context from ChromaDB historical incidents."""
        try:
            print(f"ContextGatherer: Gathering ChromaDB context for incident: {incident_data.get('id', 'unknown')}")
            print(f"ContextGatherer: Searching for similar incidents in ChromaDB...")
            
            similar_incidents, confidence = await self.chromadb_client.find_similar_incidents(
                incident_data, 
                limit=5, 
                similarity_threshold=0.7
            )
            
            print(f"ContextGatherer: Found {len(similar_incidents)} similar incidents with confidence {confidence:.3f}")
            if similar_incidents:
                for i, incident in enumerate(similar_incidents[:3]):  # Show top 3
                    print(f"ContextGatherer:   {i+1}. {incident.incident_id} (similarity: {incident.similarity_score:.3f})")
            
            return similar_incidents, confidence
            
        except Exception as e:
            print(f"ContextGatherer: Error gathering ChromaDB context: {e}")
            print(f"ContextGatherer: ChromaDB error type: {type(e).__name__}")
            return [], 0.0
    
    async def _gather_github_context(self, service_name: str) -> List[Dict[str, Any]]:
        """Gather context from GitHub recent commits."""
        try:
            print(f"ContextGatherer: Gathering GitHub context for service: {service_name}")
            
            print(f"ContextGatherer: Fetching recent commits from GitHub...")
            recent_commits = await self.github_client.get_recent_commits(
                service_name, 
                hours_back=24, 
                max_commits=10
            )
            print(f"ContextGatherer: Found {len(recent_commits)} recent commits")
            
            # Also get deployment history
            print(f"ContextGatherer: Fetching deployment history from GitHub...")
            deployment_commits = await self.github_client.get_service_deployment_history(
                service_name, 
                days_back=7
            )
            print(f"ContextGatherer: Found {len(deployment_commits)} deployment commits")
            
            # Combine and sort by timestamp
            all_commits = recent_commits + deployment_commits
            sorted_commits = sorted(
                all_commits, 
                key=lambda x: x.get('timestamp', ''), 
                reverse=True
            )
            
            result = sorted_commits[:15]  # Return top 15 most recent
            print(f"ContextGatherer: Returning {len(result)} most recent commits")
            
            return result
            
        except Exception as e:
            print(f"ContextGatherer: Error gathering GitHub context: {e}")
            print(f"ContextGatherer: GitHub error type: {type(e).__name__}")
            return []
    
    async def _gather_web_search_context(self, incident_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Gather context from web search."""
        try:
            print(f"ContextGatherer: Gathering web search context for incident: {incident_data.get('id', 'unknown')}")
            print(f"ContextGatherer: Searching web for incident knowledge...")
            
            web_knowledge = await self.web_search_client.search_incident_knowledge(incident_data)
            print(f"ContextGatherer: Found {len(web_knowledge)} web search results")
            
            if web_knowledge:
                for i, result in enumerate(web_knowledge[:3]):  # Show top 3
                    title = result.get('title', 'No title')[:50]
                    print(f"ContextGatherer:   {i+1}. {title}...")
            
            return web_knowledge
            
        except Exception as e:
            print(f"ContextGatherer: Error gathering web search context: {e}")
            print(f"ContextGatherer: Web search error type: {type(e).__name__}")
            return []
    
    def _should_trigger_web_search(
        self, 
        internal_confidence: float, 
        confidence_threshold: float,
        similar_incidents: List[Any]
    ) -> bool:
        """
        Determine whether to trigger web search based on internal confidence.
        
        Args:
            internal_confidence: Confidence score from internal knowledge (0.0-1.0)
            confidence_threshold: Threshold for triggering web search
            similar_incidents: List of similar incidents found
            
        Returns:
            True if web search should be triggered, False otherwise
        """
        # Always search if no similar incidents found
        if not similar_incidents:
            return True
        
        # Search if confidence is below threshold
        if internal_confidence < confidence_threshold:
            return True
        
        # Additional heuristics for edge cases
        # If we have incidents but they're all very old (>30 days), search for newer info
        # This would require timestamp parsing - for now, just use confidence
        
        return False
    
    def _deduplicate_logs(self, logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate log entries based on timestamp and message."""
        seen = set()
        unique_logs = []
        
        for log in logs:
            # Create a key based on timestamp and message
            key = (log.get('timestamp', ''), log.get('message', ''))
            if key not in seen:
                seen.add(key)
                unique_logs.append(log)
        
        return unique_logs
    
    async def store_incident_for_future_reference(
        self, 
        incident_data: Dict[str, Any], 
        resolution: Optional[str] = None
    ):
        """
        Store incident data in ChromaDB for future context enrichment.
        
        Args:
            incident_data: Incident data to store
            resolution: Optional resolution information
        """
        try:
            await self.chromadb_client.store_incident(incident_data, resolution)
            print(f"ContextGatherer: Stored incident {incident_data.get('id', 'unknown')} for future reference")
            
        except Exception as e:
            print(f"ContextGatherer: Error storing incident: {e}")
    
    async def get_context_stats(self) -> Dict[str, Any]:
        """Get statistics about context gathering capabilities."""
        try:
            chromadb_stats = await self.chromadb_client.get_incident_stats()
            
            return {
                'chromadb': chromadb_stats,
                'loki_configured': self.loki_client is not None,
                'github_configured': self.github_client.github is not None,
                'web_search_configured': self.web_search_client.client is not None,
                'sources_available': len([
                    s for s in [
                        self.loki_client,
                        self.chromadb_client,
                        self.github_client.github,
                        self.web_search_client.client
                    ] if s is not None
                ])
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    async def close(self):
        """Close all client connections."""
        try:
            await self.loki_client.close()
            print("ContextGatherer: Closed all client connections")
        except Exception as e:
            print(f"ContextGatherer: Error closing connections: {e}")
