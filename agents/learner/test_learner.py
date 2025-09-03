#!/usr/bin/env python3
"""
Test script for the Learner Agent
This script helps test the Learner Agent functionality by:
1. Publishing sample incidents to RabbitMQ
2. Testing the API endpoints
3. Verifying ChromaDB storage
"""

import json
import pika
import requests
import time
from typing import Dict, Any

# Configuration
RABBITMQ_HOST = 'localhost'
RABBITMQ_PORT = 5672
LEARNER_API_URL = 'http://localhost:8004'
CHROMADB_URL = 'http://localhost:8000'

def publish_incident_to_rabbitmq(incident_data: Dict[str, Any]) -> bool:
    """Publish an incident to the RabbitMQ queue for processing"""
    try:
        # Connect to RabbitMQ
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT)
        )
        channel = connection.channel()
        
        # Declare exchange and queue (same as in main.py)
        channel.exchange_declare(exchange='incidents', exchange_type='topic', durable=True)
        channel.queue_declare(queue='q.incidents.resolved', durable=True)
        channel.queue_bind(exchange='incidents', queue='q.incidents.resolved', routing_key='resolved')
        
        # Publish the incident
        message = json.dumps(incident_data)
        channel.basic_publish(
            exchange='incidents',
            routing_key='resolved',
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)  # Make message persistent
        )
        
        print(f"✓ Published incident {incident_data['id']} to RabbitMQ")
        connection.close()
        return True
        
    except Exception as e:
        print(f"✗ Error publishing incident: {e}")
        return False

def test_learner_api():
    """Test the Learner Agent API endpoints"""
    print("\n🧪 Testing Learner Agent API...")
    
    try:
        # Test health endpoint
        response = requests.get(f"{LEARNER_API_URL}/health")
        if response.status_code == 200:
            print("✓ Health endpoint working")
            print(f"  Response: {response.json()}")
        else:
            print(f"✗ Health endpoint failed: {response.status_code}")
            
        # Test stats endpoint
        response = requests.get(f"{LEARNER_API_URL}/stats")
        if response.status_code == 200:
            print("✓ Stats endpoint working")
            print(f"  Response: {response.json()}")
        else:
            print(f"✗ Stats endpoint failed: {response.status_code}")
            
        # Test search endpoint
        response = requests.get(f"{LEARNER_API_URL}/search/high%20cpu%20usage")
        if response.status_code == 200:
            print("✓ Search endpoint working")
            print(f"  Response: {response.json()}")
        else:
            print(f"✗ Search endpoint failed: {response.status_code}")
            
    except Exception as e:
        print(f"✗ API test failed: {e}")

def test_chromadb_connection():
    """Test ChromaDB connection"""
    print("\n🧪 Testing ChromaDB connection...")
    
    try:
        response = requests.get(f"{CHROMADB_URL}/api/v1/heartbeat")
        if response.status_code == 200:
            print("✓ ChromaDB is running")
        else:
            print(f"✗ ChromaDB connection failed: {response.status_code}")
    except Exception as e:
        print(f"✗ ChromaDB test failed: {e}")

def main():
    """Main test function"""
    print("🚀 Starting Learner Agent Tests")
    print("=" * 50)
    
    # Test ChromaDB connection
    test_chromadb_connection()
    
    # Test API endpoints
    test_learner_api()
    
    # Load sample incidents
    print("\n📄 Loading sample incidents...")
    try:
        with open('sample_incidents.json', 'r') as f:
            incidents = json.load(f)
        print(f"✓ Loaded {len(incidents)} sample incidents")
    except Exception as e:
        print(f"✗ Error loading sample incidents: {e}")
        return
    
    # Publish incidents to RabbitMQ
    print("\n📤 Publishing incidents to RabbitMQ...")
    for incident in incidents:
        success = publish_incident_to_rabbitmq(incident)
        if success:
            time.sleep(2)  # Wait between publications
    
    # Wait for processing
    print("\n⏳ Waiting for incidents to be processed...")
    time.sleep(10)
    
    # Test API again to see updated stats
    print("\n🧪 Testing API after processing...")
    test_learner_api()
    
    print("\n✅ Test completed!")
    print("\nTo manually test:")
    print("1. Check RabbitMQ Management UI: http://localhost:15672")
    print("2. Check Learner Agent logs for processing messages")
    print("3. Use the search API to find similar incidents")

if __name__ == "__main__":
    main()
