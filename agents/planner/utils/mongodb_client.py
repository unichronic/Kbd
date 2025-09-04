"""
MongoDB client for storing and retrieving incident response plans.
"""
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MongoDBPlanStorage:
    """MongoDB client for storing incident response plans."""
    
    def __init__(self):
        """Initialize MongoDB connection."""
        self.client = None
        self.db = None
        self.collection = None
        self._connect()
    
    def _connect(self):
        """Establish connection to MongoDB Atlas."""
        try:
            # Get MongoDB connection string from environment
            mongodb_uri = os.getenv('MONGODB_URI')
            if not mongodb_uri:
                logger.warning("MONGODB_URI not set, MongoDB storage will be disabled")
                return
            
            # Get database and collection names
            db_name = os.getenv('MONGODB_DATABASE', 'incident_response')
            collection_name = os.getenv('MONGODB_COLLECTION', 'plans')
            
            # Connect to MongoDB
            self.client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            
            # Test connection
            self.client.admin.command('ping')
            
            # Get database and collection
            self.db = self.client[db_name]
            self.collection = self.db[collection_name]
            
            # Create indexes for better performance
            self._create_indexes()
            
            logger.info(f"Connected to MongoDB Atlas: {db_name}.{collection_name}")
            
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            self.client = None
            self.db = None
            self.collection = None
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            self.client = None
            self.db = None
            self.collection = None
    
    def _create_indexes(self):
        """Create indexes for better query performance."""
        if not self.collection:
            return
        
        try:
            # Index on plan ID for fast lookups
            self.collection.create_index("id", unique=True)
            
            # Index on incident ID for finding plans by incident
            self.collection.create_index("incident_id")
            
            # Index on status for filtering by plan status
            self.collection.create_index("status")
            
            # Index on created_at for time-based queries
            self.collection.create_index("created_at")
            
            # Compound index for common queries
            self.collection.create_index([("incident_id", 1), ("status", 1)])
            
            logger.info("MongoDB indexes created successfully")
            
        except OperationFailure as e:
            logger.warning(f"Failed to create some indexes: {e}")
    
    def is_connected(self) -> bool:
        """Check if MongoDB connection is active."""
        if not self.client:
            return False
        
        try:
            self.client.admin.command('ping')
            return True
        except Exception:
            return False
    
    def save_plan(self, plan: Dict[str, Any]) -> bool:
        """
        Save a plan to MongoDB.
        
        Args:
            plan: The plan dictionary to save
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        if not self.collection:
            logger.warning("MongoDB not connected, skipping plan save")
            return False
        
        try:
            # Add metadata
            plan_doc = plan.copy()
            plan_doc['created_at'] = datetime.utcnow()
            plan_doc['updated_at'] = datetime.utcnow()
            
            # Ensure plan ID exists
            if 'id' not in plan_doc:
                plan_doc['id'] = f"plan_{plan_doc.get('incident_id', 'unknown')}_{int(datetime.utcnow().timestamp())}"
            
            # Insert or update the plan
            result = self.collection.replace_one(
                {'id': plan_doc['id']},
                plan_doc,
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                logger.info(f"Plan {plan_doc['id']} saved to MongoDB successfully")
                return True
            else:
                logger.warning(f"Plan {plan_doc['id']} was not saved (no changes)")
                return False
                
        except OperationFailure as e:
            logger.error(f"Failed to save plan to MongoDB: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving plan to MongoDB: {e}")
            return False
    
    def get_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a plan by ID.
        
        Args:
            plan_id: The plan ID to retrieve
            
        Returns:
            Dict containing the plan data, or None if not found
        """
        if not self.collection:
            logger.warning("MongoDB not connected, cannot retrieve plan")
            return None
        
        try:
            plan = self.collection.find_one({'id': plan_id})
            if plan:
                # Remove MongoDB's _id field
                plan.pop('_id', None)
                return plan
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving plan {plan_id}: {e}")
            return None
    
    def get_plans_by_incident(self, incident_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all plans for a specific incident.
        
        Args:
            incident_id: The incident ID to search for
            
        Returns:
            List of plan dictionaries
        """
        if not self.collection:
            logger.warning("MongoDB not connected, cannot retrieve plans")
            return []
        
        try:
            plans = list(self.collection.find({'incident_id': incident_id}))
            for plan in plans:
                plan.pop('_id', None)
            return plans
            
        except Exception as e:
            logger.error(f"Error retrieving plans for incident {incident_id}: {e}")
            return []
    
    def update_plan_status(self, plan_id: str, status: str, **kwargs) -> bool:
        """
        Update a plan's status and other fields.
        
        Args:
            plan_id: The plan ID to update
            status: New status for the plan
            **kwargs: Additional fields to update
            
        Returns:
            bool: True if updated successfully, False otherwise
        """
        if not self.collection:
            logger.warning("MongoDB not connected, cannot update plan")
            return False
        
        try:
            update_data = {'status': status, 'updated_at': datetime.utcnow()}
            update_data.update(kwargs)
            
            result = self.collection.update_one(
                {'id': plan_id},
                {'$set': update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"Plan {plan_id} status updated to {status}")
                return True
            else:
                logger.warning(f"Plan {plan_id} was not found for status update")
                return False
                
        except Exception as e:
            logger.error(f"Error updating plan {plan_id} status: {e}")
            return False
    
    def get_recent_plans(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent plans.
        
        Args:
            limit: Maximum number of plans to return
            
        Returns:
            List of recent plan dictionaries
        """
        if not self.collection:
            logger.warning("MongoDB not connected, cannot retrieve recent plans")
            return []
        
        try:
            plans = list(self.collection.find().sort('created_at', -1).limit(limit))
            for plan in plans:
                plan.pop('_id', None)
            return plans
            
        except Exception as e:
            logger.error(f"Error retrieving recent plans: {e}")
            return []
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")


# Global instance
mongodb_storage = MongoDBPlanStorage()
