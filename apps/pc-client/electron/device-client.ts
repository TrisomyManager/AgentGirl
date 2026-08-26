/**
 * Device Coordination Client — connects the PC client to backend
 * so 小暖 can remotely operate this device (OpenClaw-style).
 */

import { hostname } from 'os';
import { connect as wsConnect, disconnect as wsDisconnect, isConnected as wsIsConnected } from './device-ws';

const API_BASE = process.env.XIAONUAN_API_BASE_URL || 'http://127.0.0.1:8000';
const DEVICE_ID = process.env.XIAONUAN_DEVICE_ID || `pc-${hostname().toLowerCase().replace(/[^a-z0-9]/g, '-')}`;
const USER_ID = process.env.XIAONUAN_USER_ID || 'user_001';
const DEVICE_NAME = process.env.XIAONUAN_DEVICE_NAME || hostname();
const CLIENT_VERSION = '0.2.0';

const CAPABILITIES = [
  'ping', 'show_notification', 'open_url', 'get_device_status',
  'clipboard_read', 'clipboard_write', 'list_files', 'read_file',
  'write_file', 'list_processes', 'launch_app', 'screenshot', 'system_info',
];

// Tool name mapping: backend command -> local tool
const TOOL_MAP: Record<string, string> = {
  ping: 'system_info',
  show_notification: 'show_notification',
  open_url: 'open_url',
  get_device_status: 'get_device_status',
  clipboard_read: 'clipboard_read',
  clipboard_write: 'clipboard_write',
  list_files: 'list_files',
  read_file: 'read_file',
  write_file: 'write_file',
  list_processes: 'list_processes',
  launch_app: 'launch_app',
  screenshot: 'screenshot',
  system_info: 'system_info',
};

let deviceToken: string | null = null;
let pollingT: ReturnType<typeof setInterval> | null = null;
let heartbeatT: ReturnType<typeof setInterval> | null = null;
let running = false;

export function getDeviceStatus() {
  return {
    deviceId: DEVICE_ID, userId: USER_ID, deviceName: DEVICE_NAME,
    registered: !!deviceToken, running, capabilities: CAPABILITIES, version: CLIENT_VERSION,
  };
}

async function registerWithRetry(maxAttempts = 5): Promise<void> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      await registerDevice();
      console.log('[device] registered as', DEVICE_ID);
      return;
    } catch (err) {
      console.error(`[device] registration attempt ${i + 1}/${maxAttempts} failed:`, err);
      if (i < maxAttempts - 1) {
        await new Promise(r => setTimeout(r, 2000));
      }
    }
  }
  throw new Error('Device registration failed after all retries');
}

export async function startDeviceClient(): Promise<void> {
  if (running) return;
  running = true;
  try {
    await registerWithRetry();
  } catch (err) {
    console.error('[device] registration failed:', err);
    running = false;
    return;
  }
  heartbeatT = setInterval(sendHeartbeat, 10_000);

  // Try WebSocket first for real-time push
  if (deviceToken) {
    try {
      wsConnect(deviceToken, handleCommand);
      // Give WS a moment to connect; polling is the fallback
      setTimeout(() => {
        if (!wsIsConnected()) pollingT = setInterval(pollCommands, 3_000);
      }, 3000);
    } catch {
      pollingT = setInterval(pollCommands, 3_000);
    }
  } else {
    pollingT = setInterval(pollCommands, 3_000);
  }

  console.log('[device] client started');
}

export function stopDeviceClient(): void {
  running = false;
  if (heartbeatT) clearInterval(heartbeatT);
  if (pollingT) clearInterval(pollingT);
  heartbeatT = null; pollingT = null;
  wsDisconnect();
  console.log('[device] client stopped');
}

async function req(path: string, body?: Record<string, any>): Promise<any> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new Error(`${resp.status}`);
  return resp.json();
}

async function registerDevice(): Promise<void> {
  const data = await req('/device/register', {
    device_id: DEVICE_ID, user_id: USER_ID, device_type: 'pc',
    device_name: DEVICE_NAME, platform: 'app',
    capabilities: CAPABILITIES, client_version: CLIENT_VERSION,
  });
  deviceToken = data.device_token;
}

async function sendHeartbeat(): Promise<void> {
  if (!deviceToken) return;
  try { await req('/device/heartbeat', { device_id: DEVICE_ID, device_token: deviceToken }); } catch {}
}

async function pollCommands(): Promise<void> {
  if (!deviceToken) return;
  try {
    const cmd = await req('/device/commands/claim_next', { device_id: DEVICE_ID, device_token: deviceToken });
    if (!cmd || !cmd.command_id) return;
    console.log('[device] claim:', cmd.command, cmd.command_id);
    await req(`/device/commands/${cmd.command_id}/mark_running`, { device_id: DEVICE_ID, device_token: deviceToken });
    const result = await runCommand(cmd.command, cmd.payload || {});
    await req('/device/command_result', {
      device_id: DEVICE_ID, device_token: deviceToken, command_id: cmd.command_id,
      status: result.ok ? 'succeeded' : 'failed',
      result: result.ok ? result.data : undefined,
      error: result.ok ? undefined : result.message,
    });
  } catch {}
}

// WebSocket command handler — same flow as pollCommands
async function handleCommand(cmd: any): Promise<void> {
  if (!cmd || !cmd.command_id || !deviceToken) return;
  console.log('[device:ws] executing:', cmd.command, cmd.command_id);
  try {
    await req(`/device/commands/${cmd.command_id}/mark_running`, { device_id: DEVICE_ID, device_token: deviceToken });
    const result = await runCommand(cmd.command, cmd.payload || {});
    await req('/device/command_result', {
      device_id: DEVICE_ID, device_token: deviceToken, command_id: cmd.command_id,
      status: result.ok ? 'succeeded' : 'failed',
      result: result.ok ? result.data : undefined,
      error: result.ok ? undefined : result.message,
    });
  } catch {}
}

async function runCommand(cmd: string, payload: Record<string, any>): Promise<{ ok: boolean; message: string; data?: any }> {
  const toolName = TOOL_MAP[cmd] || cmd;
  try {
    const mod = await import('./tool-bridge');
    return await mod.execTool(toolName, payload);
  } catch (err: any) {
    return { ok: false, message: err.message || String(err) };
  }
}
