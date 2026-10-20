import { spawn, type ChildProcess } from 'child_process';
import { randomBytes } from 'crypto';
import { dirname, join } from 'path';
import { app, dialog } from 'electron';
import { showLocalNotification } from './notifications';

const TOOL_SERVER_SCRIPT = app.isPackaged
  ? join(process.resourcesPath, 'desktop-tools', 'server.py')
  : join(__dirname, '..', 'tools', 'server.py');
let child: ChildProcess | null = null;
let port = 0;
let token = '';
let starting: Promise<void> | null = null;
let abortStart: (() => void) | undefined;

function ensureToolServer(): Promise<void> {
  if (port && child && child.exitCode === null && !child.killed) return Promise.resolve();
  if (starting) return starting;
  token = randomBytes(32).toString('hex');
  const permitted = new Set(['PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA', 'USERPROFILE',
    'HOMEDRIVE', 'HOMEPATH', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'XIAONUAN_TOOL_CAPABILITIES', 'XIAONUAN_SANDBOX_ROOT']);
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => permitted.has(key.toUpperCase())));
  const owned = spawn(process.env.XIAONUAN_PYTHON_PATH || 'python', [TOOL_SERVER_SCRIPT, '--port', '0'], {
    cwd: dirname(TOOL_SERVER_SCRIPT), env: { ...env, XIAONUAN_TOOL_TOKEN: token, PYTHONUTF8: '1' },
    stdio: ['ignore', 'pipe', 'ignore'], windowsHide: true,
  });
  child = owned;
  starting = new Promise<void>((resolve, reject) => {
    let buffer = '', settled = false;
    const fail = () => {
      if (settled) return;
      settled = true; clearTimeout(timer); owned.kill();
      if (child === owned) { port = 0; token = ''; child = null; }
      reject(new Error('本机工具服务未能启动，请检查 Python 与工作区设置。'));
    };
    const timer = setTimeout(fail, 6000);
    abortStart = fail;
    owned.once('error', fail);
    owned.once('exit', () => {
      fail();
      if (child === owned) { child = null; port = 0; token = ''; }
    });
    owned.stdout?.on('data', (data: Buffer) => {
      if (settled) return;
      buffer += data.toString('utf8');
      if (buffer.length > 8192) { fail(); return; }
      if (!buffer.includes('\n')) return;
      try {
        const ready = JSON.parse(buffer.split('\n')[0]);
        if (ready.type !== 'ready' || !Number.isInteger(ready.port) || ready.port < 1 || ready.port > 65535) { fail(); return; }
        settled = true; clearTimeout(timer); port = ready.port; resolve();
      } catch { fail(); }
    });
  }).finally(() => { starting = null; abortStart = undefined; });
  return starting;
}

export function stopToolServer(): void {
  abortStart?.();
  child?.kill(); child = null; port = 0; token = '';
}

async function request(path: string, body?: Record<string, unknown>): Promise<any> {
  await ensureToolServer();
  const encoded = body ? JSON.stringify(body) : undefined;
  if (encoded && Buffer.byteLength(encoded) > 65536) throw new Error('工具请求过长。');
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    method: body ? 'POST' : 'GET', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: encoded, signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error('本机工具请求被拒绝。');
  return response.json();
}

export async function execTool(name: string, params: Record<string, unknown>, options?: { beforeExecute: () => Promise<boolean> }): Promise<any> {
  try {
    // Capture arguments before waiting for the local user's decision.
    const captured = JSON.parse(JSON.stringify(params));
    if (!captured || typeof captured !== 'object' || Array.isArray(captured) || Buffer.byteLength(JSON.stringify(captured)) > 60000) {
      return { ok: false, message: '工具请求格式或大小不正确。' };
    }
    const tool = (await listTools()).find(item => item.name === name);
    if (!tool) return { ok: false, message: '此能力未由本机宿主启用。' };
    let approved = false;
    if (tool.requires_confirm) {
      const destination = typeof captured.path === 'string' ? `文件：${captured.path}\n` : typeof captured.url === 'string' ? `地址：${captured.url}\n` : '';
      const details = destination + JSON.stringify(captured, null, 2);
      if (Buffer.byteLength(details) > 65536) return { ok: false, message: '工具请求过长。' };
      const choice = await dialog.showMessageBox({ type: 'question', title: '确认本机操作',
        message: tool.description, detail: details.slice(0, 2500) + (details.length > 2500 ? '\n（内容较长，仅显示开头）' : ''),
        buttons: ['取消', '允许这一次'], defaultId: 0, cancelId: 0, noLink: true });
      if (choice.response !== 1) return { ok: false, message: '已取消，本机操作未执行。' };
      approved = true;
    }
    if (options && !await options.beforeExecute()) return { ok: false, message: '请求已取消或过期，本机操作未执行。' };
    if (name === 'show_notification') {
      if (Object.keys(captured).some(key => !['title', 'body', 'text'].includes(key)) || Object.values(captured).some(value => typeof value !== 'string')) return { ok: false, message: '通知参数不正确。' };
      return await showLocalNotification(captured.title ?? '小暖', captured.body ?? captured.text);
    }
    return await request('/tools/exec', { name, params: captured, approved });
  } catch {
    return { ok: false, message: '本机工具暂时不可用，请检查本机设置。' };
  }
}

export async function listTools(): Promise<any[]> {
  const result = await request('/tools/list');
  return Array.isArray(result.tools) ? result.tools : [];
}
