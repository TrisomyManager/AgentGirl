/**
 * WebSocket transport for real-time device command push.
 * Falls back to HTTP polling when WS is unavailable.
 */

import { hostname } from 'os';

const DEVICE_ID = process.env.XIAONUAN_DEVICE_ID || `pc-${hostname().toLowerCase().replace(/[^a-z0-9]/g, '-')}`;

let ws: WebSocket | null = null;
let reconnectT: ReturnType<typeof setTimeout> | null = null;
let cmdHandler: ((cmd: any) => void) | null = null;
let wsConnected = false;

export function isConnected(): boolean { return wsConnected; }

export function connect(token: string, onCmd: (cmd: any) => void): void {
  cmdHandler = onCmd;
  const url = (process.env.XIAONUAN_WS_URL || `ws://127.0.0.1:8000`) +
    `/device/ws/${DEVICE_ID}?token=${encodeURIComponent(token)}`;

  try {
    ws = new WebSocket(url);
    ws.onopen = () => {
      wsConnected = true;
      console.log('[device:ws] connected');
      if (reconnectT) { clearTimeout(reconnectT); reconnectT = null; }
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'command' && msg.command) cmdHandler?.(msg.command);
      } catch {}
    };
    ws.onclose = () => { wsConnected = false; scheduleReconnect(); };
    ws.onerror = () => {};
  } catch { scheduleReconnect(); }
}

export function disconnect(): void {
  if (reconnectT) { clearTimeout(reconnectT); reconnectT = null; }
  wsConnected = false;
  try { ws?.close(); } catch {}
  ws = null;
}

function scheduleReconnect(): void {
  if (reconnectT) return;
  reconnectT = setTimeout(() => { reconnectT = null; }, 5000);
}
