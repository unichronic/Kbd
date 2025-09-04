import pika
import json
import redis
import uuid
import threading
import time
import os

from architect_core import generate_clarifying_questions, generate_infra_plan

# Connect to Redis
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_client = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)

def handle_new_request(ch, method, properties, body):
    """Handles the user's initial infrastructure request."""
    print(f"[+] Received new request: {body}")
    request_data = json.loads(body)
    user_prompt = request_data.get("prompt")
    
    conversation_id = str(uuid.uuid4())
    
    # Store the initial prompt in Redis
    redis_client.set(f"convo:{conversation_id}:prompt", user_prompt)
    
    # Generate clarifying questions
    questions = generate_clarifying_questions(user_prompt)
    
    # TODO: Publish questions back to the user via Collaborator Agent
    print(f"Generated questions for convo {conversation_id}: {questions}")
    ch.basic_ack(delivery_tag=method.delivery_tag)


def handle_user_answers(ch, method, properties, body):
    """Handles the user's answers and generates the final plan."""
    print(f"[+] Received user answers: {body}")
    answer_data = json.loads(body)
    conversation_id = answer_data.get("conversation_id")
    answers = answer_data.get("answers")
    
    # Retrieve the original prompt
    original_prompt = redis_client.get(f"convo:{conversation_id}:prompt")
    
    if not original_prompt:
        print(f"[!] Error: No original prompt found for conversation {conversation_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    # Generate the final IaC plan
    infra_plan = generate_infra_plan(original_prompt, answers)

    # TODO: Publish the final plan for user approval
    print(f"Generated final plan for convo {conversation_id}: {infra_plan}")
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
    connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
    channel = connection.channel()

    exchange_name = 'infra_requests'
    channel.exchange_declare(exchange=exchange_name, exchange_type='topic')

    # Consumer for new requests
    queue_new = channel.queue_declare('', exclusive=True).method.queue
    channel.queue_bind(exchange=exchange_name, queue=queue_new, routing_key='new')
    channel.basic_consume(queue=queue_new, on_message_callback=handle_new_request)

    # Consumer for user answers
    queue_answers = channel.queue_declare('', exclusive=True).method.queue
    channel.queue_bind(exchange=exchange_name, queue=queue_answers, routing_key='answers.provided')
    channel.basic_consume(queue=queue_answers, on_message_callback=handle_user_answers)

    print('[*] Waiting for messages. To exit press CTRL+C')
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    connection.close()

if __name__ == '__main__':
    main()
