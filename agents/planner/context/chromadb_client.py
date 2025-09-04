"""
ChromaDB client for historical incident context.

This module provides integration with ChromaDB for retrieving
similar past incidents and storing new incident data.
"""

import asyncio
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from models.context import SimilarIncident, ContextSource


class ChromaDBClient:
    """Client for interacting with ChromaDB for incident history."""
    
    def __init__(
        self, 
        host: str = "localhost", 
        port: int = 8002,
        collection_name: str = "incident_history",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model
        
        # Initialize ChromaDB client
        self.client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(allow_reset=True)
        )
        
        # Initialize embedding model
        self.embedding_model = SentenceTransformer(embedding_model)
        
        # Get or create collection
        self.collection = self._get_or_create_collection()
    
    def _get_or_create_collection(self):
        """Get existing collection or create a new one."""
        try:
            # Try to get existing collection
            collection = self.client.get_collection(self.collection_name)
            print(f"ChromaDB: Using existing collection '{self.collection_name}'")
            return collection
        except Exception:
            # Create new collection if it doesn't exist
            collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Historical incident data for context enrichment"}
            )
            print(f"ChromaDB: Created new collection '{self.collection_name}'")
            return collection
    
    async def find_similar_incidents(
        self, 
        incident_data: Dict[str, Any], 
        limit: int = 5,
        similarity_threshold: float = 0.7
    ) -> tuple[List[SimilarIncident], float]:
        """
        Find similar past incidents based on incident description.
        
        Args:
            incident_data: Current incident data
            limit: Maximum number of similar incidents to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            Tuple of (list of similar incidents, confidence score)
        """
        try:
            # Create search text from incident data
            search_text = self._create_search_text(incident_data)
            
            # Generate embedding for search
            search_embedding = self.embedding_model.encode([search_text])
            
            # Query ChromaDB
            results = self.collection.query(
                query_embeddings=search_embedding.tolist(),
                n_results=limit,
                include=["metadatas", "distances", "documents"]
            )
            
            similar_incidents = []
            confidence_score = 0.0
            
            if results['ids'] and results['ids'][0]:
                for i, (incident_id, distance, metadata, document) in enumerate(zip(
                    results['ids'][0],
                    results['distances'][0],
                    results['metadatas'][0],
                    results['documents'][0]
                )):
                    # Convert distance to similarity score (ChromaDB uses cosine distance)
                    similarity_score = 1 - distance
                    
                    if similarity_score >= similarity_threshold:
                        similar_incident = SimilarIncident(
                            incident_id=incident_id,
                            title=metadata.get('title', 'Unknown'),
                            summary=document,
                            resolution=metadata.get('resolution'),
                            similarity_score=similarity_score,
                            timestamp=metadata.get('timestamp'),
                            service=metadata.get('service')
                        )
                        similar_incidents.append(similar_incident)
                
                # Calculate confidence score based on best match
                if similar_incidents:
                    # Use the highest similarity score as confidence
                    confidence_score = max(incident.similarity_score for incident in similar_incidents)
                    
                    # Boost confidence if we have multiple good matches
                    if len(similar_incidents) > 1:
                        avg_similarity = sum(incident.similarity_score for incident in similar_incidents) / len(similar_incidents)
                        confidence_score = min(1.0, confidence_score + (avg_similarity * 0.1))
            
            print(f"ChromaDB: Found {len(similar_incidents)} similar incidents with confidence {confidence_score:.3f}")
            return similar_incidents, confidence_score
            
        except Exception as e:
            print(f"ChromaDB: Error finding similar incidents: {e}")
            return [], 0.0
    
    def _create_search_text(self, incident_data: Dict[str, Any]) -> str:
        """Create searchable text from incident data."""
        parts = []
        
        if incident_data.get('title'):
            parts.append(incident_data['title'])
        
        if incident_data.get('hypothesis'):
            parts.append(incident_data['hypothesis'])
        
        if incident_data.get('symptoms'):
            parts.extend(incident_data['symptoms'])
        
        if incident_data.get('affected_service'):
            parts.append(f"service: {incident_data['affected_service']}")
        
        # Add log messages if available
        if incident_data.get('logs'):
            for log in incident_data['logs'][:10]:  # Limit to first 10 logs
                if isinstance(log, dict) and log.get('message'):
                    parts.append(log['message'])
        
        return " ".join(parts)
    
    async def store_incident(self, incident_data: Dict[str, Any], resolution: Optional[str] = None):
        """
        Store a new incident in ChromaDB for future reference.
        
        Args:
            incident_data: Incident data to store
            resolution: Optional resolution information
        """
        try:
            # Create document text
            document_text = self._create_search_text(incident_data)
            
            # Generate embedding
            embedding = self.embedding_model.encode([document_text])
            
            # Prepare metadata
            metadata = {
                'title': incident_data.get('title', 'Unknown'),
                'service': incident_data.get('affected_service', 'unknown'),
                'timestamp': incident_data.get('timestamp', str(asyncio.get_event_loop().time())),
                'severity': incident_data.get('derived', {}).get('severity', 'unknown')
            }
            
            if resolution:
                metadata['resolution'] = resolution
            
            # Store in ChromaDB
            self.collection.add(
                ids=[incident_data['id']],
                embeddings=embedding.tolist(),
                metadatas=[metadata],
                documents=[document_text]
            )
            
            print(f"ChromaDB: Stored incident {incident_data['id']}")
            
        except Exception as e:
            print(f"ChromaDB: Error storing incident {incident_data.get('id', 'unknown')}: {e}")
    
    async def get_incident_stats(self) -> Dict[str, Any]:
        """Get statistics about stored incidents."""
        try:
            count = self.collection.count()
            return {
                'total_incidents': count,
                'collection_name': self.collection_name,
                'embedding_model': self.embedding_model_name
            }
        except Exception as e:
            print(f"ChromaDB: Error getting stats: {e}")
            return {'error': str(e)}
