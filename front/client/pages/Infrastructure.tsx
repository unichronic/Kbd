import React, { useState, useRef, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  Cloud, 
  Server, 
  Database, 
  Network, 
  Shield, 
  Code, 
  MessageSquare,
  CheckCircle,
  Clock,
  AlertCircle,
  Send,
  Bot,
  User
} from 'lucide-react';

interface ChatMessage {
  id: string;
  type: 'user' | 'bot';
  content: string;
  timestamp: string;
  source?: 'gemini' | 'fallback';
}

interface ConversationState {
  id: string;
  status: 'asking' | 'generating' | 'completed';
  currentQuestion: number;
  questions: string[];
  answers: string[];
  generatedInfra?: string;
  source?: 'gemini' | 'fallback';
  downloadUrl?: string;
}

interface InfraRequest {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  createdAt: string;
  questions?: string[];
  answers?: Record<string, string>;
  generatedCode?: string;
}

export default function Infrastructure() {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      type: 'bot',
      content: 'Hi! I\'m your Infrastructure Setup Assistant. I\'ll help you create a complete infrastructure setup by asking you a few questions. What would you like to deploy?',
      timestamp: new Date().toISOString()
    }
  ]);
  
  const [conversation, setConversation] = useState<ConversationState | null>(null);
  const [currentInput, setCurrentInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages]);

  const simulateTyping = (message: string, delay: number = 1000, source?: 'gemini' | 'fallback') => {
    setIsLoading(true);
    setTimeout(() => {
      const botMessage: ChatMessage = {
        id: Date.now().toString(),
        type: 'bot',
        content: message,
        timestamp: new Date().toISOString(),
        source
      };
      setChatMessages(prev => [...prev, botMessage]);
      setIsLoading(false);
    }, delay);
  };

  const handleSendMessage = async () => {
    if (!currentInput.trim()) return;

    // Add user message
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: currentInput,
      timestamp: new Date().toISOString()
    };
    
    setChatMessages(prev => [...prev, userMessage]);
    setCurrentInput('');

    // Handle conversation flow
    if (!conversation) {
      // First message - start conversation and analyze initial input for context
      const initialInput = currentInput.toLowerCase();
      
      // Pre-fill answers based on initial input context
      const preFilledAnswers: Record<string, string> = {};
      
      // Detect cloud provider
      if (initialInput.includes('aws')) preFilledAnswers.cloudProvider = 'AWS';
      else if (initialInput.includes('gcp') || initialInput.includes('google')) preFilledAnswers.cloudProvider = 'GCP';
      else if (initialInput.includes('azure')) preFilledAnswers.cloudProvider = 'Azure';
      
      // Detect application type
      if (initialInput.includes('node') || initialInput.includes('nodejs')) preFilledAnswers.appType = 'Node.js';
      else if (initialInput.includes('python')) preFilledAnswers.appType = 'Python';
      else if (initialInput.includes('react')) preFilledAnswers.appType = 'React';
      else if (initialInput.includes('java')) preFilledAnswers.appType = 'Java';
      
      // Detect environment
      if (initialInput.includes('staging')) preFilledAnswers.environment = 'staging';
      else if (initialInput.includes('production') || initialInput.includes('prod')) preFilledAnswers.environment = 'production';
      else if (initialInput.includes('development') || initialInput.includes('dev')) preFilledAnswers.environment = 'development';
      
      // Detect database needs
      if (initialInput.includes('postgres')) preFilledAnswers.database = 'PostgreSQL';
      else if (initialInput.includes('mysql')) preFilledAnswers.database = 'MySQL';
      else if (initialInput.includes('mongo')) preFilledAnswers.database = 'MongoDB';
      
      // Generate questions using Gemini-powered backend
      const newConversation: ConversationState = {
        id: Date.now().toString(),
        status: 'asking',
        currentQuestion: 0,
        questions: [],
        answers: [currentInput, ...Object.values(preFilledAnswers)]
      };
      
      setConversation(newConversation);
      
      // Show a more natural acknowledgment
      simulateTyping("Let me understand what you need and see what additional information might be helpful...", 1000);
      
      // Generate questions using Gemini backend
      setTimeout(async () => {
        try {
          const response = await fetch('http://localhost:8005/api/infrastructure/questions', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              prompt: currentInput
            })
          });

          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          const data = await response.json();
          const generatedQuestions = data.questions || [];
          const source = data.source;
          
          const updatedConversation = {
            ...newConversation,
            questions: generatedQuestions,
            source
          };
          
          setConversation(updatedConversation);
          
          if (generatedQuestions.length > 0) {
            // Ask the first question naturally
            simulateTyping(generatedQuestions[0], 1500, source);
          } else {
            // Ready to generate infrastructure
            updatedConversation.status = 'generating';
            setConversation(updatedConversation);
            simulateTyping("Perfect! I have enough information to generate your infrastructure setup...", 1000);
            
            setTimeout(async () => {
              const { infrastructure: infraCode, source } = await generateInfrastructure(currentInput, Object.values(preFilledAnswers));
              setConversation({
                ...updatedConversation,
                status: 'completed',
                generatedInfra: infraCode,
                source
              });
              simulateTyping(infraCode, 2000, source);
            }, 3000);
          }
        } catch (error) {
          console.error('Error generating questions:', error);
          simulateTyping("I'm having trouble connecting to the AI backend. Please ensure the API Gateway is running on port 8005 with GEMINI_API_KEY configured.", 2000);
        }
      }, 2000);
    } else {
      // Continue conversation
      const updatedAnswers = [...conversation.answers, currentInput];
      const nextQuestion = conversation.currentQuestion + 1;
      
      if (nextQuestion < conversation.questions.length) {
        // Ask next question
        setConversation({
          ...conversation,
          currentQuestion: nextQuestion,
          answers: updatedAnswers
        });
        simulateTyping(conversation.questions[nextQuestion], 1000, conversation.source);
      } else {
        // All questions answered, generate infrastructure
        setConversation({
          ...conversation,
          status: 'generating',
          answers: updatedAnswers
        });
        
        simulateTyping("Perfect! I have all the information I need. Let me generate your infrastructure setup...", 1000);
        
        // Simulate infrastructure generation
        setTimeout(async () => {
          const result = await generateInfrastructure(conversation.answers[0], updatedAnswers.slice(1));
          const { infrastructure: infraCode, source } = result;
          setConversation({
            ...conversation,
            status: 'completed',
            answers: updatedAnswers,
            generatedInfra: infraCode,
            source
          });
          simulateTyping(infraCode, 2000, source);
        }, 3000);
      }
    }
  };

  const generateInfrastructure = async (originalPrompt: string, answers: string[]): Promise<{ infrastructure: string; source: 'gemini' | 'fallback' }> => {
    try {
      const response = await fetch('http://localhost:8005/api/infrastructure/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          original_prompt: originalPrompt,
          answers: answers
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return { infrastructure: data.infrastructure, source: data.source };
    } catch (error) {
      console.error('Error generating infrastructure:', error);
      // Fallback to basic template on error
      return {
        infrastructure: `## Dockerfile
   \`\`\`dockerfile
   FROM node:18-alpine
   WORKDIR /app
   COPY package*.json ./
   RUN npm install
   COPY . .
   EXPOSE 3000
   CMD ["npm", "start"]
   \`\`\`

   ## Error
   Failed to connect to Gemini-powered backend. Please ensure:
   1. Backend API Gateway is running on port 8005
   2. GEMINI_API_KEY is set in environment
   3. Network connectivity is available`,
        source: 'fallback'
      };
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleCreatePackage = async () => {
    if (!conversation.generatedInfra) return;

    try {
      const response = await fetch('http://localhost:8005/api/infrastructure/deploy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ infrastructure_code: conversation.generatedInfra }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setConversation(prev => ({
        ...prev,
        downloadUrl: data.download_url,
      }));

    } catch (error) {
      console.error('Error creating deployment package:', error);
      // You might want to show an error message in the UI
      console.error('Error creating deployment package:', error);
    }
  };

  const resetConversation = () => {
    setConversation(null);
    setChatMessages([
      {
        id: '1',
        type: 'bot',
        content: 'Hi! I\'m your Infrastructure Setup Assistant. I\'ll help you create a complete infrastructure setup by asking you a few questions. What would you like to deploy?',
        timestamp: new Date().toISOString()
      }
    ]);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Infrastructure Setup Assistant</h1>
          <p className="text-muted-foreground">
            AI-powered chatbot for infrastructure as code generation
          </p>
        </div>
        <Button onClick={resetConversation} variant="outline">
          <MessageSquare className="mr-2 h-4 w-4" />
          New Conversation
        </Button>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col">
        <ScrollArea className="flex-1 p-6">
          <div className="space-y-4 max-w-4xl mx-auto">
            {chatMessages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-3 ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {message.type === 'bot' && (
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                      <Bot className="w-4 h-4 text-primary" />
                    </div>
                  </div>
                )}
                
                <div
                  className={`max-w-[70%] rounded-lg px-4 py-2 ${
                    message.type === 'user'
                      ? 'bg-primary text-primary-foreground ml-auto'
                      : 'bg-muted'
                  }`}
                >
                  {message.type === 'user' ? (
                    <p className="text-sm">{message.content}</p>
                  ) : (
                    <div className="prose prose-sm dark:prose-invert max-w-full">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          pre: ({node, ...props}) => <pre className="bg-background p-3 rounded text-xs overflow-x-auto border" {...props} />,
                          code: ({node, ...props}) => <code className="" {...props} />,
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  )}
                  
                  {/* Show Create Package button after infrastructure code is generated */}
                  {message.type === 'bot' && message.content.includes('##') && conversation?.status === 'completed' && !conversation.downloadUrl && (
                    <div className="flex justify-center mt-4">
                      <button 
                        onClick={handleCreatePackage}
                        className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded-lg transition-colors duration-200 ease-in-out"
                      >
                        Create Deploy Package
                      </button>
                    </div>
                  )}
                  
                  {/* Show download link after package is created */}
                  {message.type === 'bot' && message.content.includes('##') && conversation?.downloadUrl && (
                    <div className="text-center mt-4">
                      <a 
                        href={`http://localhost:8003${conversation.downloadUrl}`}
                        download
                        className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded-lg transition-colors duration-200 ease-in-out no-underline"
                      >
                        Download Deploy Package
                      </a>
                    </div>
                  )}
                  
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs opacity-70">
                      {new Date(message.timestamp).toLocaleTimeString()}
                    </span>
                    {message.source && (
                      <Badge variant={message.source === 'gemini' ? 'default' : 'secondary'}>
                        {message.source === 'gemini' ? 'Gemini' : 'Fallback'}
                      </Badge>
                    )}
                  </div>
                </div>
                
                {message.type === 'user' && (
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                      <User className="w-4 h-4 text-primary" />
                    </div>
                  </div>
                )}
              </div>
            ))}
            
            {isLoading && (
              <div className="flex gap-3 justify-start">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <Bot className="w-4 h-4 text-primary" />
                  </div>
                </div>
                <div className="bg-muted rounded-lg px-4 py-2">
                  <div className="flex-grow overflow-y-auto p-6 space-y-4">
                    {conversation.status === 'completed' && conversation.generatedInfra && (
                      <div className="flex justify-center">
                        <button 
                          onClick={handleCreatePackage}
                          className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded-lg transition-colors duration-200 ease-in-out"
                        >
                          Create Deploy Package
                        </button>
                      </div>
                    )}
                    {conversation.downloadUrl && (
                      <div className="text-center">
                        <a 
                          href={`http://localhost:8003${conversation.downloadUrl}`}
                          download
                          className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded-lg transition-colors duration-200 ease-in-out no-underline"
                        >
                          Download Deploy Package
                        </a>
                      </div>
                    )}
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input Area */}
        <div className="border-t p-4">
          <div className="max-w-4xl mx-auto">
            <div className="flex gap-2">
              <Input
                value={currentInput}
                onChange={(e) => setCurrentInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={
                  conversation?.status === 'completed' 
                    ? "Start a new conversation..." 
                    : "Type your message..."
                }
                disabled={isLoading || conversation?.status === 'generating'}
                className="flex-1"
              />
              <Button 
                onClick={handleSendMessage} 
                disabled={!currentInput.trim() || isLoading || conversation?.status === 'generating'}
                size="icon"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
            
            {conversation && (
              <div className="mt-2 text-xs text-muted-foreground">
                {conversation.status === 'asking' && (
                  <span>Question {conversation.currentQuestion + 1} of {conversation.questions.length}</span>
                )}
                {conversation.status === 'generating' && (
                  <span>Generating your infrastructure setup...</span>
                )}
                {conversation.status === 'completed' && (
                  <span>Infrastructure setup completed! Start a new conversation for another setup.</span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
