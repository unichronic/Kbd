FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONPATH=/app
ENV RABBITMQ_HOST=rabbitmq
ENV REDIS_HOST=redis

# Run the application
CMD ["python", "main.py"]
