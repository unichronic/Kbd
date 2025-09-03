// API client for communicating with the backend API gateway

const API_BASE_URL = 'http://localhost:8005';

export interface HealthStatus {
  gateway: string;
  agents: Record<string, {
    status: string;
    response?: any;
    error?: string;
  }>;
  timestamp: number;
}

export interface AgentInfo {
  name: string;
  url: string;
  description: string;
}

export interface Incident {
  id: string;
  title: string;
  severity: 'critical' | 'warning' | 'info';
  status: 'active' | 'acknowledged' | 'resolved';
  hypothesis: string;
  occurredAt: string;
  service: string;
  updated?: string;
}

export interface QueueStatus {
  proposed_queue: {
    name: string;
    message_count: number;
  };
  approved_queue: {
    name: string;
    message_count: number;
  };
}

export interface ForwardPlansResponse {
  status: string;
  forwarded_count: number;
  message: string;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  async getHealth(): Promise<HealthStatus> {
    return this.request<HealthStatus>('/api/health');
  }

  async getAgents(): Promise<AgentInfo[]> {
    const response = await this.request<{ agents: AgentInfo[] }>('/api/agents');
    return response.agents;
  }

  async getIncidents(): Promise<Incident[]> {
    const response = await this.request<{ incidents: Incident[] }>('/api/incidents');
    return response.incidents;
  }

  async getQueueStatus(): Promise<QueueStatus> {
    return this.request<QueueStatus>('/api/plans/queue-status');
  }

  async forwardPlansToApproved(): Promise<ForwardPlansResponse> {
    return this.request<ForwardPlansResponse>('/api/plans/forward-to-approved', {
      method: 'POST',
    });
  }

  async submitQuery(query: { query: string }): Promise<any> {
    return this.request('/api/query', {
      method: 'POST',
      body: JSON.stringify(query),
    });
  }

  async getStats(): Promise<any> {
    return this.request('/api/stats');
  }
}

export const apiClient = new ApiClient();
