import { spawn, ChildProcess } from 'child_process';
import { join } from 'path';

const TOOL_SERVER_SCRIPT = join(__dirname, '..', 'tools', 'server.py');
const TOOL_SERVER_PORT = 18721;

let toolServerProcess: ChildProcess | null = null;
let serverReady = false;

function ensureToolServer(): void {
  if (toolServerProcess && !toolServerProcess.killed && serverReady) return;

  toolServerProcess = spawn('python', [TOOL_SERVER_SCRIPT, '--port', String(TOOL_SERVER_PORT)], {
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });

  toolServerProcess.stdout?.on('data', (d: Buffer) => {
    const text = d.toString();
    if (text.includes('ready') || text.includes('started')) serverReady = true;
  });

  toolServerProcess.on('exit', () => {
    serverReady = false;
  });
}

async function fetchFromServer(path: string, options?: RequestInit): Promise<any> {
  ensureToolServer();
  // Wait up to 3s for server to be ready
  const start = Date.now();
  while (!serverReady && Date.now() - start < 3000) {
    await new Promise((r) => setTimeout(r, 100));
  }
  const resp = await fetch(`http://127.0.0.1:${TOOL_SERVER_PORT}${path}`, options);
  return resp.json();
}

export async function execTool(name: string, params: Record<string, any>): Promise<any> {
  return fetchFromServer('/tools/exec', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, params }),
  });
}

export async function listTools(): Promise<any[]> {
  return fetchFromServer('/tools/list');
}
