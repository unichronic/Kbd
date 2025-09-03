#!/usr/bin/env python3
"""
Simple test script to publish a sample incident to test Notion integration
"""

import json
import pika
import time

def publish_test_incident():
    """Publish a test incident to RabbitMQ"""
    try:
        # Connect to RabbitMQ
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host='localhost', port=5672)
        )
        channel = connection.channel()
        
        # Declare exchange and queue
        channel.exchange_declare(exchange='incidents', exchange_type='topic', durable=True)
        channel.queue_declare(queue='q.incidents.resolved', durable=True)
        channel.queue_bind(exchange='incidents', queue='q.incidents.resolved', routing_key='resolved')
        
        # Load sample incident
        with open('sample_incident.json', 'r') as f:
            incident_data = json.load(f)
        
        # Publish the incident
        message = json.dumps(incident_data)
        channel.basic_publish(
            exchange='incidents',
            routing_key='resolved',
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        
        print(f"✓ Published test incident {incident_data['id']} to RabbitMQ")
        print("Check the Learner Agent logs to see if it processes successfully!")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"✗ Error publishing incident: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Notion Integration")
    print("=" * 30)
    
    success = publish_test_incident()
    
    if success:
        print("\n✅ Test incident published!")
        print("Check your Notion database: https://www.notion.so/0c64c04e75b24837bcf5f34a4c51667d")
    else:
        print("\n❌ Failed to publish test incident")
