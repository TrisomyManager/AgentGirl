import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, globalShortcut, protocol, net } from 'electron';
import { join, resolve, relative, isAbsolute, sep } from 'path';
import { pathToFileURL } from 'url';
import { mkdirSync } from 'fs';
import Store from 'electron-store';
import { startDeviceClient, stopDeviceClient, getDeviceStatus } from './device-client';
import { execTool, listTools, stopToolServer } from './tool-bridge';
import { closeNotifications, setNotificationActivator, showLocalNotification } from './notifications';

if (process.env.XIAONUAN_PROFILE_DIR) {
  const profile = process.env.XIAONUAN_PROFILE_DIR;
  if (!isAbsolute(profile)) throw new Error('桌面资料目录必须是绝对路径。');
  mkdirSync(profile, { recursive: true });
  app.setPath('userData', profile);
}

protocol.registerSchemesAsPrivileged([{ scheme: 'app', privileges: {
  standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true,
} }]);

function registerApplicationAssets() {
  const root = resolve(__dirname, '../dist');
  protocol.handle('app', async request => {
    try {
      const url = new URL(request.url);
      if (url.hostname !== 'companion' || url.username || url.password || !['GET', 'HEAD'].includes(request.method)) {
        return new Response('Not found', { status: 404 });
      }
      const pathname = decodeURIComponent(url.pathname);
      if (pathname.includes('\\') || pathname.includes('\0')) return new Response('Not found', { status: 404 });
      const filename = resolve(root, pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, ''));
      const scoped = relative(root, filename);
      if (scoped === '..' || scoped.startsWith('..' + sep) || isAbsolute(scoped)) return new Response('Not found', { status: 404 });
      return await net.fetch(pathToFileURL(filename).toString());
    } catch { return new Response('Not found', { status: 404 }); }
  });
}

const store = new Store({
  defaults: {
    windowBounds: { width: 1200, height: 800 },
    autoLaunch: false,
  },
});

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let isQuitting = false;

// ── Tray icon (programmatic 16x16 PNG) ────────────────────────────────

function createTrayIcon(): Electron.NativeImage {
  // 16x16 RGBA favicon: warm coral circle with a heart center
  const size = 16;
  const buf = Buffer.alloc(size * size * 4);
  const cx = 7.5, cy = 7.5, r = 7;

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      const dx = x - cx, dy = y - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist <= r) {
        // Coral circle
        buf[i] = 120;   // B (native bitmap uses premultiplied BGRA)
        buf[i + 1] = 140; // G
        buf[i + 2] = 255; // R
        buf[i + 3] = 255; // A
      } else {
        buf[i + 3] = 0;  // transparent
      }
    }
  }

  return nativeImage.createFromBitmap(buf, { width: size, height: size });
}

// ── Window ────────────────────────────────────────────────────────────

function createWindow() {
  const { width, height } = store.get('windowBounds') as { width: number; height: number };

  mainWindow = new BrowserWindow({
    width,
    height,
    minWidth: 640,
    minHeight: 480,
    title: '小暖 · 智能陪伴',
    show: false,
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (url !== mainWindow?.webContents.getURL()) event.preventDefault();
  });

  mainWindow.once('ready-to-show', () => mainWindow?.show());

  mainWindow.on('resize', () => {
    if (mainWindow && !mainWindow.isMaximized()) {
      const bounds = mainWindow.getBounds();
      store.set('windowBounds', { width: bounds.width, height: bounds.height });
    }
  });

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow?.hide();
    }
  });

  const devUrl = !app.isPackaged && process.env.VITE_DEV_SERVER_URL;
  if (devUrl) void mainWindow.loadURL(devUrl);
  else void mainWindow.loadURL('app://companion/');
}

// ── Tray ──────────────────────────────────────────────────────────────

function createTray() {
  const icon = createTrayIcon();
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: '打开小暖', click: () => { mainWindow?.show(); mainWindow?.focus(); } },
    {
      label: '开机自启',
      type: 'checkbox',
      checked: store.get('autoLaunch') as boolean,
      click: (mi) => {
        const checked = (mi as any).checked;
        store.set('autoLaunch', checked);
        app.setLoginItemSettings({ openAtLogin: checked });
      },
    },
    { type: 'separator' },
    { label: '退出', click: () => { isQuitting = true; app.quit(); } },
  ]);

  tray.setToolTip('小暖 · 智能陪伴');
  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => { mainWindow?.show(); mainWindow?.focus(); });
}

// ── IPC ───────────────────────────────────────────────────────────────

function setupIPC() {
  function trusted(event: Electron.IpcMainEvent | Electron.IpcMainInvokeEvent) {
    return !!mainWindow && event.sender === mainWindow.webContents && event.senderFrame === mainWindow.webContents.mainFrame;
  }
  function requireTrusted(event: Electron.IpcMainInvokeEvent) {
    if (!trusted(event)) throw new Error('请求来源不受信任。');
  }
  ipcMain.handle('store:get', (event, key: string) => { requireTrusted(event); return ['windowBounds', 'autoLaunch'].includes(key) ? store.get(key) : undefined; });
  ipcMain.handle('store:set', (event, key: string, value: any) => { requireTrusted(event); if (['windowBounds', 'autoLaunch'].includes(key)) store.set(key, value); });

  ipcMain.handle('tool:exec', async (_e, name: string, params: Record<string, any>) => {
    requireTrusted(_e);
    return execTool(name, params);
  });

  ipcMain.handle('tool:list', async (event) => {
    requireTrusted(event);
    return listTools();
  });

  ipcMain.handle('device:status', (event) => { requireTrusted(event); return getDeviceStatus(); });

  ipcMain.handle('app:autoLaunch', (_e, enabled?: boolean) => {
    requireTrusted(_e);
    if (typeof enabled === 'boolean') {
      store.set('autoLaunch', enabled);
      app.setLoginItemSettings({ openAtLogin: enabled });
    }
    return store.get('autoLaunch');
  });

  function notify(_e: Electron.IpcMainEvent, title: string, body: string, background: boolean) {
    if (!trusted(_e) || typeof title !== 'string' || typeof body !== 'string' || title.length > 100 || body.length > 2000) return;
    if (background && mainWindow?.isVisible() && mainWindow.isFocused()) return;
    void showLocalNotification(title, body);
  }
  ipcMain.on('notification:show', (event, title, body) => notify(event, title, body, false));
  ipcMain.on('notification:background', (event, title, body) => notify(event, title, body, true));
}

// ── App lifecycle ─────────────────────────────────────────────────────

app.whenReady().then(() => {
  registerApplicationAssets();
  if (process.platform === 'win32') app.setAppUserModelId('com.companion.xiaonuan');
  setNotificationActivator(() => { mainWindow?.show(); mainWindow?.focus(); });
  setupIPC();
  createWindow();
  createTray();

  // Apply saved auto-launch preference
  if (store.get('autoLaunch')) {
    app.setLoginItemSettings({ openAtLogin: true });
  }

  // Register this device with the backend so 小暖 can control it
  startDeviceClient();

  globalShortcut.register('Ctrl+Shift+X', () => {
    if (mainWindow?.isVisible() && mainWindow.isFocused()) {
      mainWindow.hide();
    } else {
      mainWindow?.show();
      mainWindow?.focus();
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else mainWindow?.show();
  });
});

app.on('window-all-closed', () => {});

app.on('before-quit', () => {
  isQuitting = true;
  stopDeviceClient();
  stopToolServer();
  closeNotifications();
  globalShortcut.unregisterAll();
});
