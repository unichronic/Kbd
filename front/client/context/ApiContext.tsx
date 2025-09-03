import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { apiClient, HealthStatus, AgentInfo } from '@/lib/api';
import { wsService, MessageHandler } from '@/lib/websocket';

interface ApiContextType {
  // API client
  apiClient: typeof apiClient;
  
  // Connection state
  isOnline: boolean;
  isApiConnected: boolean;
  wsConnectionState: string;
  
  // Health data
  healthStatus: HealthStatus | null;
  agents: AgentInfo[];
  
  // Loading states
  isLoading: boolean;
  error: string | null;
  
  // Actions
  refreshHealth: () => Promise<void>;
  refreshAgents: () => Promise<void>;
  clearError: () => void;
}

const ApiContext = createContext<ApiContextType | null>(null);

export function ApiProvider({ children }: { children: ReactNode }) {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [isApiConnected, setIsApiConnected] = useState(false);
  const [wsConnectionState, setWsConnectionState] = useState('disconnected');
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Handle online/offline state
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      setError(null);
    };
    const handleOffline = () => {
      setIsOnline(false);
      setError('Network connection lost');
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // WebSocket connection state monitoring
  useEffect(() => {
    const handleConnectionChange: MessageHandler = (data) => {
      setWsConnectionState(wsService.getConnectionState());
      setIsApiConnected(wsService.isConnected());
    };

    const handleReconnectFailed: MessageHandler = (data) => {
      setError('Failed to establish real-time connection');
    };

    wsService.on('connected', handleConnectionChange);
    wsService.on('reconnect_failed', handleReconnectFailed);

    // Initial connection
    wsService.connect();
    setWsConnectionState(wsService.getConnectionState());

    return () => {
      wsService.off('connected', handleConnectionChange);
      wsService.off('reconnect_failed', handleReconnectFailed);
    };
  }, []);

  // Initial data loading
  useEffect(() => {
    if (isOnline) {
      refreshHealth();
      refreshAgents();
    }
  }, [isOnline]);

  const refreshHealth = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const health = await apiClient.getHealth();
      setHealthStatus(health);
      setIsApiConnected(true);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch health status';
      setError(errorMessage);
      setIsApiConnected(false);
    } finally {
      setIsLoading(false);
    }
  };

  const refreshAgents = async () => {
    try {
      setError(null);
      const agentsData = await apiClient.getAgents();
      setAgents(agentsData);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch agents';
      setError(errorMessage);
    }
  };

  const clearError = () => {
    setError(null);
  };

  const value: ApiContextType = {
    apiClient,
    isOnline,
    isApiConnected,
    wsConnectionState,
    healthStatus,
    agents,
    isLoading,
    error,
    refreshHealth,
    refreshAgents,
    clearError,
  };

  return (
    <ApiContext.Provider value={value}>
      {children}
    </ApiContext.Provider>
  );
}

export function useApi() {
  const context = useContext(ApiContext);
  if (!context) {
    throw new Error('useApi must be used within ApiProvider');
  }
  return context;
}
