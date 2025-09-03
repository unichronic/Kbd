// WebSocket service for real-time communication

export interface MessageHandler {
  (data: any): void;
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private connectionState = 'disconnected';

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      // For now, we'll use a mock WebSocket connection
      // In a real implementation, you'd connect to your WebSocket server
      this.connectionState = 'connecting';
      this.emit('connecting');
      
      // Simulate connection after a short delay
      setTimeout(() => {
        this.connectionState = 'connected';
        this.emit('connected');
      }, 100);
      
    } catch (error) {
      this.connectionState = 'disconnected';
      this.emit('reconnect_failed');
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.connectionState = 'disconnected';
  }

  on(event: string, handler: MessageHandler) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, []);
    }
    this.handlers.get(event)!.push(handler);
  }

  off(event: string, handler: MessageHandler) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  private emit(event: string, data?: any) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach(handler => handler(data));
    }
  }

  getConnectionState(): string {
    return this.connectionState;
  }

  isConnected(): boolean {
    return this.connectionState === 'connected';
  }

  send(data: any) {
    if (this.isConnected()) {
      // In a real implementation, you'd send data through the WebSocket
      console.log('WebSocket send:', data);
    } else {
      console.warn('WebSocket not connected, cannot send data');
    }
  }
}

export const wsService = new WebSocketService();
