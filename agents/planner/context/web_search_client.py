"""
Web search client for public knowledge context.

This module provides integration with web search APIs for retrieving
public knowledge about incidents, error messages, and solutions.
"""

import asyncio
from typing import Any, Dict, List, Optional
from tavily import TavilyClient
from ..models.context import ContextSource


class WebSearchClient:
    """Client for web search to gather public knowledge."""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        max_results: int = 5,
        timeout: int = 10
    ):
        self.api_key = api_key
        self.max_results = max_results
        self.timeout = timeout
        self.client = None
        
        if api_key:
            self.client = TavilyClient(api_key=api_key)
    
    async def search_incident_knowledge(
        self, 
        incident_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Search for public knowledge about an incident.
        
        Args:
            incident_data: Current incident data
            
        Returns:
            List of relevant web search results
        """
        if not self.client:
            print("WebSearch: No API key configured")
            return []
        
        try:
            # Create search queries from incident data
            search_queries = self._create_search_queries(incident_data)
            
            all_results = []
            
            for query in search_queries:
                try:
                    # Search with Tavily
                    response = self.client.search(
                        query=query,
                        search_depth="basic",
                        max_results=self.max_results,
                        include_domains=["stackoverflow.com", "github.com", "kubernetes.io", "docs.aws.amazon.com"]
                    )
                    
                    if response and 'results' in response:
                        for result in response['results']:
                            search_result = {
                                'title': result.get('title', ''),
                                'url': result.get('url', ''),
                                'content': result.get('content', ''),
                                'score': result.get('score', 0.0),
                                'query': query,
                                'source': 'web_search'
                            }
                            all_results.append(search_result)
                
                except Exception as e:
                    print(f"WebSearch: Error searching for '{query}': {e}")
                    continue
            
            # Remove duplicates and sort by relevance
            unique_results = self._deduplicate_results(all_results)
            sorted_results = sorted(unique_results, key=lambda x: x['score'], reverse=True)
            
            print(f"WebSearch: Retrieved {len(sorted_results)} relevant results")
            return sorted_results[:self.max_results * 2]  # Return top results
            
        except Exception as e:
            print(f"WebSearch: Error in incident knowledge search: {e}")
            return []
    
    def _create_search_queries(self, incident_data: Dict[str, Any]) -> List[str]:
        """Create search queries from incident data."""
        queries = []
        
        # Base query from title and service
        if incident_data.get('title'):
            queries.append(f"{incident_data['title']} kubernetes solution")
        
        if incident_data.get('affected_service'):
            service = incident_data['affected_service']
            queries.append(f"{service} error troubleshooting kubernetes")
        
        # Query from symptoms
        if incident_data.get('symptoms'):
            for symptom in incident_data['symptoms'][:3]:  # Limit to first 3 symptoms
                queries.append(f"{symptom} kubernetes fix")
        
        # Query from error logs
        if incident_data.get('logs'):
            error_messages = []
            for log in incident_data['logs'][:5]:  # Check first 5 logs
                if isinstance(log, dict):
                    message = log.get('message', '')
                    if any(keyword in message.lower() for keyword in ['error', 'exception', 'panic', 'fatal']):
                        # Extract key error terms
                        words = message.split()[:10]  # First 10 words
                        error_terms = [w for w in words if len(w) > 3 and w.isalpha()]
                        if error_terms:
                            error_query = f"{' '.join(error_terms[:5])} kubernetes"
                            error_messages.append(error_query)
            
            queries.extend(error_messages[:2])  # Add up to 2 error-based queries
        
        # Query from hypothesis
        if incident_data.get('hypothesis'):
            queries.append(f"{incident_data['hypothesis']} kubernetes resolution")
        
        return queries[:5]  # Limit to 5 queries total
    
    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate search results based on URL."""
        seen_urls = set()
        unique_results = []
        
        for result in results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        return unique_results
    
    async def search_error_solutions(
        self, 
        error_message: str, 
        service_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for solutions to specific error messages.
        
        Args:
            error_message: The error message to search for
            service_name: Optional service name for context
            
        Returns:
            List of solution-related search results
        """
        if not self.client:
            return []
        
        try:
            # Create focused search query
            if service_name:
                query = f"{error_message} {service_name} kubernetes solution"
            else:
                query = f"{error_message} kubernetes solution"
            
            response = self.client.search(
                query=query,
                search_depth="advanced",
                max_results=self.max_results,
                include_domains=["stackoverflow.com", "github.com", "kubernetes.io"]
            )
            
            results = []
            if response and 'results' in response:
                for result in response['results']:
                    search_result = {
                        'title': result.get('title', ''),
                        'url': result.get('url', ''),
                        'content': result.get('content', ''),
                        'score': result.get('score', 0.0),
                        'query': query,
                        'source': 'web_search',
                        'type': 'error_solution'
                    }
                    results.append(search_result)
            
            print(f"WebSearch: Found {len(results)} solutions for error: {error_message[:50]}...")
            return results
            
        except Exception as e:
            print(f"WebSearch: Error searching for error solutions: {e}")
            return []
    
    async def search_best_practices(
        self, 
        topic: str, 
        service_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for best practices related to a topic.
        
        Args:
            topic: The topic to search for
            service_name: Optional service name for context
            
        Returns:
            List of best practice search results
        """
        if not self.client:
            return []
        
        try:
            query = f"{topic} best practices kubernetes"
            if service_name:
                query += f" {service_name}"
            
            response = self.client.search(
                query=query,
                search_depth="basic",
                max_results=self.max_results,
                include_domains=["kubernetes.io", "docs.aws.amazon.com", "cloud.google.com"]
            )
            
            results = []
            if response and 'results' in response:
                for result in response['results']:
                    search_result = {
                        'title': result.get('title', ''),
                        'url': result.get('url', ''),
                        'content': result.get('content', ''),
                        'score': result.get('score', 0.0),
                        'query': query,
                        'source': 'web_search',
                        'type': 'best_practices'
                    }
                    results.append(search_result)
            
            print(f"WebSearch: Found {len(results)} best practice results for: {topic}")
            return results
            
        except Exception as e:
            print(f"WebSearch: Error searching for best practices: {e}")
            return []
