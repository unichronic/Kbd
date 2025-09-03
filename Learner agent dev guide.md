# **End-to-End Build Guide for the Learner Agent**

This guide provides a comprehensive plan for building, implementing, and testing the Learner Agent from start to finish. The core focus is on creating its "evolving memory" system, which allows the entire platform to learn from past incidents.

## **1\. Core Purpose & Workflow**

The Learner Agent acts as the long-term memory for KubeMinder AI. Its workflow is triggered *after* an incident is resolved.

**Workflow:**

1. **Consume:** It listens for a message on the q.incidents.resolved queue. This message contains the complete story of an incident: the initial alert, the AI's analysis, the action taken, and the outcome.  
2. **Document:** It automatically generates a post-mortem document in Notion, creating a human-readable record.  
3. **Memorize:** It converts a summary of the incident into a numerical representation (a vector embedding) and stores it in a specialized vector database (ChromaDB).

This "memory" evolves because the **Planner Agent** will later query this database to find similar past incidents, improving its future diagnoses.

## **2\. Architecture & Tech Stack**

The Learner Agent is a Python service composed of a few key components:

* **RabbitMQ Consumer (pika):** The entry point. Listens for resolved incidents.  
* **Vectorization Engine (sentence-transformers):** The "brain" that converts text summaries into vector embeddings.  
* **Vector Database (ChromaDB):** The long-term memory where embeddings are stored.  
* **Notion Client (notion-client):** The "scribe" that writes post-mortems.

## **3\. Step-by-Step Implementation Plan**

### **Step 1: Project Setup**

1. **Create Agent Directory:** Inside your monorepo, create the directory /agents/learner/.  
2. **Set up Dependencies:** Create a requirements.txt file inside /agents/learner/ with the following:  
   fastapi  
   uvicorn  
   pika  
   sentence-transformers  
   chromadb-client  
   notion-client

3. **Set up ChromaDB:** The easiest way to run ChromaDB is with Docker. Add it to your docker-compose.yml file:  
   \# In your docker-compose.yml  
   services:  
     rabbitmq:  
       \# ... existing rabbitmq config ...  
     chromadb:  
       image: chromadb/chroma  
       container\_name: chromadb  
       ports:  
         \- "8000:8000"

   Run docker-compose up \-d again to start the ChromaDB container.

### **Step 2: Consume Resolved Incidents**

In /agents/learner/main.py, set up the RabbitMQ consumer as defined in the setup guide. You'll need a callback function to process the messages.

\# /agents/learner/main.py  
import pika  
import json

def process\_resolved\_incident(channel, method, properties, body):  
    """Callback function to handle incoming messages."""  
    print("Received a resolved incident.")  
    incident\_data \= json.loads(body)  
      
    \# 1\. Document the incident in Notion  
    \# create\_notion\_post\_mortem(incident\_data)  
      
    \# 2\. Memorize the incident in ChromaDB  
    \# memorize\_incident(incident\_data)  
      
    \# Acknowledge the message  
    channel.basic\_ack(delivery\_tag=method.delivery\_tag)

\# RabbitMQ connection and channel setup as per the guide...  
\# ...  
\# Ensure the queue 'q.incidents.resolved' and its binding exist

channel.basic\_consume(queue='q.incidents.resolved', on\_message\_callback=process\_resolved\_incident)  
print("Learner Agent is waiting for resolved incidents...")  
channel.start\_consuming()

### **Step 3: Memorize the Incident (Vectorization)**

This is the core of the evolving memory.

1. **Create a Summary:** First, create a function to generate a concise, descriptive summary of the incident. This is what the AI will "remember".  
   def create\_incident\_summary(incident\_data):  
       """Creates a text summary for vectorization."""  
       alert \= incident\_data.get('alert', {})  
       analysis \= incident\_data.get('analysis', {})  
       action \= incident\_data.get('action', {})

       return (  
           f"Symptom: {alert.get('name', 'N/A')} on service {alert.get('service', 'N/A')}. "  
           f"Root Cause: {analysis.get('hypothesis', 'N/A')}. "  
           f"Fix: Executed action '{action.get('name', 'N/A')}'."  
       )

2. **Implement the memorize\_incident function:** This function will use the sentence-transformers library to convert the summary into a vector and store it in ChromaDB.  
   from sentence\_transformers import SentenceTransformer  
   import chromadb

   \# Load the model once when the agent starts  
   embedding\_model \= SentenceTransformer('all-MiniLM-L6-v2')  
   chroma\_client \= chromadb.HttpClient(host='localhost', port=8000)

   \# Ensure the collection exists  
   collection \= chroma\_client.get\_or\_create\_collection("incidents")

   def memorize\_incident(incident\_data):  
       """Generates embedding and stores it in ChromaDB."""  
       incident\_id \= incident\_data.get('id', 'unknown-id')  
       summary \= create\_incident\_summary(incident\_data)

       \# 1\. Create the embedding  
       embedding \= embedding\_model.encode(summary).tolist()

       \# 2\. Store in ChromaDB  
       collection.add(  
           embeddings=\[embedding\],  
           documents=\[summary\],  
           metadatas=\[{"service": incident\_data.get('alert', {}).get('service')}\],  
           ids=\[incident\_id\]  
       )  
       print(f"Memorized incident {incident\_id}.")

### **Step 4: Document in Notion**

Implement the create\_notion\_post\_mortem function to automatically generate documentation.

import os  
from notion\_client import Client

\# Assumes NOTION\_API\_KEY and NOTION\_DATABASE\_ID are in environment variables  
notion \= Client(auth=os.environ.get("NOTION\_API\_KEY"))  
database\_id \= os.environ.get("NOTION\_DATABASE\_ID")

def create\_notion\_post\_mortem(incident\_data):  
    """Creates a new page in a Notion database."""  
    \# ... code to format incident\_data into Notion's block structure ...  
      
    \# notion.pages.create(  
    \#     parent={"database\_id": database\_id},  
    \#     properties={...}, \# Title, tags, etc.  
    \#     children=\[...\]   \# The formatted content  
    \# )  
    print(f"Created Notion post-mortem for incident {incident\_data.get('id')}.")

## **4\. End-to-End Testing Strategy**

Since the other agents aren't built yet, you need to simulate their output to test the Learner.

1. **Prepare a Sample Incident:** Create a JSON file with a sample resolved incident message.  
   // sample\_incident.json  
   {  
     "id": "INC-2025-09-03-001",  
     "alert": {  
       "name": "High CPU Usage",  
       "service": "auth-service"  
     },  
     "analysis": {  
       "hypothesis": "A memory leak in the v1.2.1 deployment caused excessive garbage collection."  
     },  
     "action": {  
       "name": "Rollback to v1.2.0"  
     }  
   }

2. **Manually Publish the Message:**  
   * Go to the RabbitMQ Management UI (http://localhost:15672).  
   * Navigate to **Exchanges** \-\> click on **incidents**.  
   * In the **Publish message** panel:  
     * Set **Routing key** to resolved.  
     * Paste the content of your sample\_incident.json into the **Payload**.  
   * Click **Publish message**.  
3. **Verify the Outcome:**  
   * **Agent Log:** Your running Learner Agent's console should print the "Received...", "Memorized...", and "Created..." messages.  
   * **Notion:** A new page should appear in your designated Notion database.  
   * **ChromaDB:** You can write a small separate script to query ChromaDB to confirm the new vector was added.