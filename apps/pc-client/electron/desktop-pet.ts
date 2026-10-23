import { app, BrowserWindow, dialog, ipcMain, Menu, net, powerMonitor, protocol, screen } from 'electron';
import type { IpcMainInvokeEvent } from 'electron';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readPetPack } from './pet-pack';
import type { PetPack } from './pet-pack';

protocol.registerSchemesAsPrivileged([{ scheme: 'companion-pet', privileges: {
  standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true,
} }]);

interface PetStore { get(key: string): any; set(key: string, value: any): void }

export function setupDesktopPet(store: PetStore, getMain: () => BrowserWindow | null) {
  let pet: BrowserWindow | null = null;
  let pack: PetPack | null = null;
  let moving = false;
  let locked = false;
  const media = new Map<string, string>();
  let publicPack: any = null;
  let positionTimer: ReturnType<typeof setTimeout> | undefined;
  const trusted = (event: IpcMainInvokeEvent) => {
    if (event.sender !== getMain()?.webContents && event.sender !== pet?.webContents) throw new Error('Unknown window');
  };
  const mainOnly = (event: IpcMainInvokeEvent) => {
    if (event.sender !== getMain()?.webContents) throw new Error('Main window required');
  };

  protocol.handle('companion-pet', request => {
    const url = new URL(request.url);
    const file = url.hostname === 'asset' ? media.get(url.pathname.slice(1)) : undefined;
    return file ? net.fetch(pathToFileURL(file).toString(), { headers: request.headers })
      : new Response('Not found', { status: 404 });
  });

  async function loadPack(directory: string) {
    const next = await readPetPack(directory);
    const nextMedia = new Map<string, string>();
    const clips = next.clips.map(({ path, ...clip }) => {
      const token = randomUUID();
      nextMedia.set(token, path);
      return { ...clip, url: `companion-pet://asset/${token}` };
    });
    pack = next;
    media.clear();
    for (const [key, value] of nextMedia) media.set(key, value);
    publicPack = { name: next.name, width: next.width, height: next.height, bodyBox: next.bodyBox, clips };
    store.set('petPackPath', directory);
    pet?.webContents.send('pet:pack', publicPack);
    return publicPack;
  }

  function clampPosition(x: number, y: number) {
    const area = screen.getDisplayNearestPoint({ x: Math.round(x), y: Math.round(y) }).workArea;
    const bounds = pet!.getBounds();
    return [Math.max(area.x, Math.min(area.x + area.width - bounds.width, Math.round(x))),
      Math.max(area.y, Math.min(area.y + area.height - bounds.height, Math.round(y)))];
  }

  async function show() {
    if (pet && !pet.isDestroyed()) { pet.showInactive(); return; }
    pet = new BrowserWindow({ width: 380, height: 290, transparent: true, frame: false,
      alwaysOnTop: true, skipTaskbar: true, resizable: false, show: false,
      webPreferences: { preload: join(__dirname, 'pet-preload.js'), contextIsolation: true,
        nodeIntegration: false, sandbox: true } });
    pet.setMenu(null);
    const area = screen.getPrimaryDisplay().workArea;
    const saved = store.get('petPosition') as { x: number; y: number } | undefined;
    const [x, y] = clampPosition(saved?.x ?? area.x + area.width - 400, saved?.y ?? area.y + area.height - 310);
    pet.setPosition(x, y);
    pet.setIgnoreMouseEvents(Boolean(store.get('petClickThrough')), { forward: true });
    pet.on('closed', () => { pet = null; moving = false; });
    pet.on('moved', () => {
      if (!pet) return;
      const [px, py] = pet.getPosition();
      if (positionTimer) clearTimeout(positionTimer);
      positionTimer = setTimeout(() => store.set('petPosition', { x: px, y: py }), 250);
    });
    pet.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    pet.webContents.on('will-navigate', event => event.preventDefault());
    pet.once('ready-to-show', () => pet?.showInactive());
    const dev = process.env.VITE_DEV_SERVER_URL;
    if (dev) {
      const url = new URL(dev); url.searchParams.set('view', 'pet'); await pet.loadURL(url.toString());
    } else await pet.loadFile(join(__dirname, '../dist/index.html'), { query: { view: 'pet' } });
    store.set('petEnabled', true);
  }

  ipcMain.handle('pet:status', event => {
    trusted(event);
    return { enabled: !!pet, clickThrough: Boolean(store.get('petClickThrough')), pack: publicPack };
  });
  ipcMain.handle('pet:choose-pack', async event => {
    mainOnly(event);
    const choice = await dialog.showOpenDialog(getMain()!, { title: '选择 dsh-pet 角色或 videos 目录', properties: ['openDirectory'] });
    return choice.canceled ? publicPack : loadPack(choice.filePaths[0]);
  });
  ipcMain.handle('pet:enabled', async (event, enabled: boolean) => {
    mainOnly(event);
    if (typeof enabled !== 'boolean') throw new Error('Invalid value');
    if (enabled) await show();
    else { pet?.close(); store.set('petEnabled', false); }
    return { enabled: !!pet };
  });
  ipcMain.handle('pet:click-through', (event, enabled: boolean) => {
    mainOnly(event);
    if (typeof enabled !== 'boolean') throw new Error('Invalid value');
    store.set('petClickThrough', enabled); pet?.setIgnoreMouseEvents(enabled, { forward: true });
  });
  ipcMain.handle('pet:move', (event, dx: number, dy: number) => {
    if (event.sender !== pet?.webContents) throw new Error('Pet window required');
    if (![dx, dy].every(Number.isFinite) || Math.abs(dx) > 100 || Math.abs(dy) > 100) return;
    moving = true;
    const [x, y] = pet.getPosition(); pet.setPosition(...clampPosition(x + dx, y + dy) as [number, number]);
  });
  ipcMain.handle('pet:drag-end', event => { trusted(event); moving = false; });
  ipcMain.handle('pet:menu', event => {
    trusted(event);
    Menu.buildFromTemplate([
      { label: '打开对话', click: () => { getMain()?.show(); getMain()?.focus(); } },
      { label: '隐藏桌宠', click: () => { pet?.close(); store.set('petEnabled', false); } },
    ]).popup({ window: pet ?? undefined });
  });
  ipcMain.handle('pet:bubble', (event, text: string, emotion?: string) => {
    mainOnly(event);
    if (typeof text !== 'string') return;
    pet?.webContents.send('pet:bubble', { text: text.slice(0, 500), emotion: typeof emotion === 'string' ? emotion.slice(0, 32) : '' });
  });
  ipcMain.handle('companion:context', async event => {
    mainOnly(event);
    // Private, fixed helper: it is never registered as a remotely callable tool.
    let context: Record<string, unknown> = { available: false };
    try {
      const helper = app.isPackaged ? join(process.resourcesPath, 'tools/foreground_context.py')
        : join(__dirname, '../tools/foreground_context.py');
      const result = await promisify(execFile)('python', [helper],
        { windowsHide: true, timeout: 3000, maxBuffer: 4096, encoding: 'utf8' });
      context = JSON.parse(result.stdout);
    } catch { /* Unsupported OS or missing local Python: disable observations. */ }
    return { ...context,
      idle_seconds: powerMonitor.getSystemIdleTime(), locked, interacting: moving };
  });
  powerMonitor.on('lock-screen', () => { locked = true; pet?.hide(); });
  powerMonitor.on('unlock-screen', () => { locked = false; if (store.get('petEnabled')) pet?.showInactive(); });
  powerMonitor.on('suspend', () => { locked = true; pet?.hide(); });
  powerMonitor.on('resume', () => { locked = false; if (store.get('petEnabled')) pet?.showInactive(); });

  return {
    async restore() {
      const directory = store.get('petPackPath');
      if (typeof directory === 'string') {
        try { await loadPack(directory); } catch (error) { console.warn('[pet] Pack unavailable:', error); }
      }
      if (store.get('petEnabled')) await show();
    },
    recover() { store.set('petClickThrough', false); pet?.setIgnoreMouseEvents(false); void show(); },
  };
}
