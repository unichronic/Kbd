import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.0-flash')

def generate_clarifying_questions(user_prompt):
    """Uses Gemini 2.0 Flash to generate contextual questions or responses."""
    
    prompt = f"""
    You are a helpful Infrastructure Setup Assistant having a natural conversation with a user.
    
    User said: "{user_prompt}"

    Your task is to understand what they want and respond naturally. You have two options:

    1. If they've provided enough information to start building infrastructure, respond with: {{"action": "generate", "message": "I have enough information to start building your infrastructure setup."}}

    2. If you need more information, ask 1-2 specific, conversational questions based on what they've told you. Focus on the most important missing details for their specific use case.

    Consider these aspects only if relevant:
    - Application type/technology stack
    - Cloud provider preference  
    - Environment (dev/staging/prod)
    - Scale/traffic expectations
    - Database needs
    - Security requirements

    Respond naturally and conversationally. Don't ask generic questions - tailor them to their specific request.

    Return a JSON object with either:
    - {{"action": "ask", "questions": ["specific question 1", "specific question 2"]}}
    - {{"action": "generate", "message": "Ready to generate message"}}
    """
    
    try:
        response = model.generate_content(prompt)
        questions_text = response.text.strip()
        
        # Extract JSON from response if it's wrapped in markdown
        if "```json" in questions_text:
            questions_text = questions_text.split("```json")[1].split("```")[0].strip()
        elif "```" in questions_text:
            questions_text = questions_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(questions_text)
        
        # Convert to old format for backward compatibility
        if result.get("action") == "ask":
            return result["questions"]
        elif result.get("action") == "generate":
            return []  # Empty array signals ready to generate
        else:
            return result  # Fallback to original format
            
    except Exception as e:
        print(f"[!] Error generating questions with Gemini: {e}")
        # Fallback to contextual questions
        return [
            "What type of application are you building?",
            "Which cloud provider would you prefer?"
        ]


def generate_infra_plan(original_prompt, answers):
    """Uses Gemini 2.0 Flash to generate comprehensive infrastructure setup files."""
    
    prompt = f"""
    You are an Infra Setup Expert.  
    You strictly follow this accepted list:  

    infra_setup = {{
        "Networking": ["VPC", "Subnet", "Firewall", "DNS"],
        "Compute": ["VM", "Container", "Kubernetes"],
        "Storage": ["Postgres", "MySQL", "MongoDB", "S3"],
        "Application": ["Backend", "Frontend", "API", "Reverse Proxy"],
        "Security": ["SSL", "Secrets Manager", "IAM"],
        "CI/CD": ["GitHub Actions", "Jenkins", "GitLab CI"],
        "Monitoring": ["Prometheus", "Grafana", "ELK", "Loki", "Alerts"],
        "Scaling": ["Auto Scaling", "Load Balancer", "Caching", "CDN"]
    }}

    The user's original request was: "{original_prompt}"
    They have provided the following answers to your clarifying questions:
    {answers}

    Based on this information, generate the **infra setup files** step by step:

    1. **Application Layer** → Provide a Dockerfile (to containerize the app).  
    2. **Compute Layer** → Provide Terraform configs to run that container (EC2, ECS, or Kubernetes).  
    3. **Networking Layer** → Add Terraform configs for VPC, Subnet, Firewall, DNS if required.  
    4. **Storage Layer** → Add DB setup (Terraform RDS or Docker-compose for local Postgres).  
    5. **Security Layer** → Add SSL, IAM, or Secrets Manager config.  
    6. **CI/CD Layer** → Provide GitHub Actions or Jenkinsfile to build & deploy.  
    7. **Monitoring Layer** → Provide Prometheus/Grafana setup (YAML, Helm, or Docker-compose).  
    8. **Scaling Layer** → Add Terraform configs for Auto Scaling and Load Balancer.  

    Output should be in **ready-to-use code blocks** with clear file names and structure.
    
    IMPORTANT: strictly follow this format for each file:
    
    filename.ext
    ```
    file content here
    ```
    
    Example:
    
    Dockerfile
    ```
    FROM node:18-alpine
    WORKDIR /app
    COPY package*.json ./
    RUN npm install
    COPY . .
    EXPOSE 3000
    CMD ["npm", "start"]
    ```
    
    docker-compose.yml
    ```
    version: "3.9"
    services:
      app:
        build: .
        ports:
          - "3000:3000"
    ```
    
    Generate all necessary files for a complete infrastructure setup.
    """
    
    try:
        response = model.generate_content(prompt)
        infra_files = response.text.strip()
        
        # Return the complete infrastructure setup with all files
        return infra_files
    except Exception as e:
        print(f"[!] Error generating infrastructure plan with Gemini: {e}")
        # Fallback to basic infrastructure template
        return """## Dockerfile
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

## terraform/main.tf
```hcl
variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
  
  tags = {
    Name        = "${var.environment}-web-server"
    Environment = var.environment
  }
}

output "instance_ip" {
  value = aws_instance.web.public_ip
}
```

## docker-compose.yml
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
  
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```"""
