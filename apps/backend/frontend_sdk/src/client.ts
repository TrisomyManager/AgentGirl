import WebSocket from 'ws';
import {
  type CompanionConfig,
  type ConnectionHandler,
  type ErrorHandler,
  type MessageHandler,
  type SendMessageRequest,
  type TurnMessage,
  Platform,
} from './types';

export class CompanionClient {
  private ws?: WebSocket;
  private config: Required<CompanionConfig>;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private heartbeatTimer?: ReturnType<typeof setInterval>;
  private isConnected = false;
  private isIntentionalClose = false;

  onMessage: MessageHandler | null = null;
  onConnectionChange: ConnectionHandler | null = null;
  onError: ErrorHandler | null = null;

  constructor(config: CompanionConfig) {
    this.config = {
      wsPath: '/gateway/ws',
      apiPath: '/gateway',
      platform: Platform.APP,
      reconnectInterval: 3000,
      heartbeatInterval: 30000,
      language: 'zh-CN',
      ...config,
    };
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${this.config.gatewayUrl.replace(/^http/, 'ws')}${this.config.wsPath}/${this.config.userId}`;

    try {
      this.ws = new WebSocket(wsUrl);
    } catch (err) {
      this.onError?.(err as Error);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.isConnected = true;
      this.isIntentionalClose = false;
      this.onConnectionChange?.(true);
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      try {
        const msg: TurnMessage = JSON.parse(event.data as string);
        this.onMessage?.(msg);
      } catch (err) {
        this.onError?.(new Error(`Failed to parse message: ${err}`));
      }
    };

    this.ws.onerror = (err) => {
      this.onError?.(new Error(`WebSocket error: ${err.message}`));
    };

    this.ws.onclose = () => {
      this.isConnected = false;
      this.stopHeartbeat();
      this.onConnectionChange?.(false);
      if (!this.isIntentionalClose) {
        this.scheduleReconnect();
      }
    };
  }

  disconnect(): void {
    this.isIntentionalClose = true;
    this.clearReconnect();
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = undefined;
    this.isConnected = false;
    this.onConnectionChange?.(false);
  }

  async sendMessage(req: SendMessageRequest): Promise<void> {
    if (!this.isConnected || !this.ws) {
      throw new Error('Not connected');
    }

    const payload = {
      type: 'send',
      user_id: this.config.userId,
      platform: this.config.platform,
      ...req,
    };

    this.ws.send(JSON.stringify(payload));
  }

  async sendVoice(audioBlob: Blob): Promise<void> {
    const reader = new FileReader();
    const base64 = await new Promise<string>((resolve, reject) => {
      reader.onloadend = () => {
        const dataUrl = reader.result as string;
        resolve(dataUrl.split(',')[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(audioBlob);
    });

    await this.sendMessage({
      content: '',
      has_voice: true,
      voice_data_b64: base64,
    });
  }

  async getHistory(sessionId: string): Promise<TurnMessage[]> {
    const url = `${this.config.gatewayUrl}${this.config.apiPath}/sessions/${this.config.userId}/history?session_id=${sessionId}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  private scheduleReconnect(): void {
    this.clearReconnect();
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, this.config.reconnectInterval);
  }

  private clearReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.ws?.send(JSON.stringify({ type: 'ping' }));
    }, this.config.heartbeatInterval);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = undefined;
    }
  }
}
