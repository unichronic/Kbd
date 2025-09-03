# **Development Plan for KubeMinder AI Agents**

This document provides a step-by-step guide for building the five core agents of the KubeMinder AI platform. The approach is aligned with the MVP plan, focusing on delivering value incrementally.

## **Foundational Setup (Prerequisites)**

Before building the individual agents, the core infrastructure for communication must be in place.

1. **Set up RabbitMQ:** This will serve as the central message bus. You will define exchanges (e.g., incidents, plans) and have agents consume from queues bound to these exchanges to handle events like incidents.new, incidents.triaged, plans.proposed, plans.approved, and incidents.resolved.  
2. **Establish Microservice Skeletons:** Setup monorepo and base project structures for each agent. Using Python with FastAPI is a good default, with Go as a specialized option for the Observer.  
3. **Containerize Everything:** Set up Dockerfiles for each agent from the beginning to ensure a consistent environment.

## **Agent 1: The Observer**

**Core Responsibility:** To ingest data from all external sources and publish standardized "incident" events.

* **Tech Stack:** Go (recommended for high-performance I/O), RabbitMQ client library (e.g., streadway/amqp).  
* **Development Steps:**  
  1. **(MVP)** Build a connector for **Prometheus**. This service will listen for alerts from Prometheus Alertmanager.  
  2. **(MVP)** Build a connector for **Loki**. This will be used by the Planner initially, but the Observer should own the connection logic.  
  3. **(MVP)** Upon receiving a Prometheus alert, create a standardized JSON event containing the alert details and publish it to the incidents exchange with the routing key new.  
  4. **(Post-MVP)** Add connectors for **GitHub** (to listen for commits/PRs via webhooks) and **Notion** (to pull documentation).  
  5. **(Post-MVP)** Enhance the events with more contextual data from these new sources before publishing.

## **Agent 2: The Planner**

**Core Responsibility:** To analyze incidents, perform root cause analysis, and propose solutions.

* **Tech Stack:** Python, FastAPI, LangChain, Kimi K2 (or another LLM), RabbitMQ client (e.g., pika).  
* **Development Steps:**  
  1. **(MVP)** Create a RabbitMQ consumer that listens to a queue bound to the incidents exchange with the routing key new.  
  2. **(MVP)** When a new incident event is received, use the Loki connector to query for logs from the affected service around the time of the alert.  
  3. **(MVP)** Implement the core **AI Triage** logic: Use **LangChain** to create a prompt that combines the Prometheus alert data and the relevant Loki log snippets.  
  4. **(MVP)** Send this prompt to the **Kimi K2** LLM API to get a natural language root cause hypothesis.  
  5. **(MVP)** Publish the original incident data enriched with the AI hypothesis to the incidents exchange with the routing key triaged.  
  6. **(Post-MVP)** Enhance the context gathering to also pull data from GitHub and the Learner Agent's database before building the prompt.  
  7. **(Post-MVP)** Evolve the LLM interaction to not just find the cause, but to formulate a concrete remediation plan and a risk score, publishing it to the plans exchange with the routing key proposed.

## **Agent 3: The Collaborator**

**Core Responsibility:** To manage all user interactions, from answering queries to handling approvals.

* **Tech Stack:** Python, FastAPI, WebSocket library, RabbitMQ client (e.g., pika).  
* **Development Steps:**  
  1. **(MVP)** Build a REST API endpoint for the frontend to submit natural language queries (e.g., POST /api/query).  
  2. **(MVP)** This endpoint will perform simple, read-only actions, like fetching current metrics from Prometheus, and return the data. This provides the "Conversational Control" for status checks.  
  3. **(MVP)** Create a WebSocket connection. The service will consume incidents.triaged events from RabbitMQ and push them to the frontend dashboard in real-time.  
  4. **(Post-MVP)** Integrate with the **PagerDuty API** to trigger alerts when a critical plan is proposed.  
  5. **(Post-MVP)** Integrate with **Slack/MS Teams SDKs** to send the proposed plan and interactive "Approve/Deny" buttons to a designated channel.  
  6. **(Post-MVP)** When a user clicks "Approve," publish the plan to the plans exchange with the routing key approved.

## **Agent 4: The Actor (Post-MVP)**

**Core Responsibility:** To execute approved remediation plans on the infrastructure.

* **Tech Stack:** Python, FastAPI, Kubernetes client, Cloud SDKs (Boto3, etc.), RabbitMQ client (e.g., pika).  
* **Development Steps:**  
  1. Create a RabbitMQ consumer that listens to a queue bound to the plans exchange with the routing key approved.  
  2. Implement the **"AFK Mode" logic**. The agent will check the user's configured autonomy level against the risk score of the plan before proceeding.  
  3. Build a library of "execution modules" that can perform specific actions:  
     * A **Kubernetes module** that uses the official client to perform actions like kubectl rollout undo or kubectl scale.  
     * An **AWS module** that uses Boto3 to perform actions like restarting an EC2 instance.  
  4. Upon successful execution, publish a confirmation event to the incidents exchange with the routing key resolved.

## **Agent 5: The Learner (Post-MVP)**

**Core Responsibility:** To document resolved incidents and update the AI's knowledge base.

* **Tech Stack:** Python, FastAPI, ChromaDB, Notion API client, RabbitMQ client (e.g., pika).  
* **Development Steps:**  
  1. Create a RabbitMQ consumer that listens to a queue bound to the incidents exchange with the routing key resolved.  
  2. When an incident is resolved, gather all the data associated with it (initial alert, logs, RCA, and the successful action).  
  3. Use the **Notion API** to automatically generate a post-mortem document from this data and save it to the user's workspace.  
  4. Use a sentence-transformer model to convert a summary of the incident (symptom, cause, fix) into a vector embedding.  
  5. Store this embedding in the **ChromaDB** vector database. This database will be queried by the Planner Agent in the future to find similar past incidents.