/**
 * WebSocket transport for real-time device command push.
 * Falls back to HTTP polling when WS is unavailable.
 */

import { hostname } from 'os';
import WebSocket from 'ws';

const DEVICE_ID = process.env.XIAONUAN_DEVICE_ID || `pc-${hostname().toLowerCase().replace(/[^a-z0-9]/g, '-')}`;

let ws: WebSocket | null = null;
let reconnectT: ReturnType<typeof setTimeout> | null = null;
let cmdHandler: ((cmd: any) => void) | null = null;
let wsConnected = false;
let generation = 0;
let activeToken = '';

export function isConnected(): boolean { return wsConnected; }

export function connect(token: string, onCmd: (cmd: any) => void): void {
  disconnect();
  activeToken = token;
  cmdHandler = onCmd;
  openSocket();
}

function openSocket(): void {
  if (!activeToken) return;
  const current = generation;
  const base = process.env.XIAONUAN_WS_URL || (process.env.XIAONUAN_API_BASE_URL || 'http://127.0.0.1:8000').replace(/^http/, 'ws');
  const url = base.replace(/\/$/, '') + `/device/ws/${encodeURIComponent(DEVICE_ID)}`;

  try {
    const socket = new WebSocket(url, ['companion.device', activeToken]);
    ws = socket;
    ws.onopen = () => {
      if (current !== generation) { socket.close(); return; }
      wsConnected = true;
      console.log('[device:ws] connected');
      if (reconnectT) { clearTimeout(reconnectT); reconnectT = null; }
    };
    ws.onmessage = (ev) => {
      if (current !== generation) return;
      try {
        const msg = JSON.parse(ev.data.toString());
        if (msg.type === 'command' && msg.command) cmdHandler?.(msg.command);
      } catch {}
    };
    ws.onclose = () => { if (current === generation) { wsConnected = false; scheduleReconnect(); } };
    ws.onerror = () => {};
  } catch { scheduleReconnect(); }
}

export function disconnect(): void {
  generation++;
  activeToken = ''; cmdHandler = null;
  if (reconnectT) { clearTimeout(reconnectT); reconnectT = null; }
  wsConnected = false;
  try { ws?.close(); } catch {}
  ws = null;
}

function scheduleReconnect(): void {
  if (reconnectT || !activeToken) return;
  reconnectT = setTimeout(() => { reconnectT = null; openSocket(); }, 5000);
}
