import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, globalShortcut, Notification } from 'electron';
import { join } from 'path';
import Store from 'electron-store';
import { startDeviceClient, stopDeviceClient, getDeviceStatus } from './device-client';

const store = new Store({
  defaults: {
    windowBounds: { width: 1200, height: 800 },
    autoLaunch: true,
  },
});

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let isQuitting = false;

// ── Tray icon (programmatic 16x16 PNG) ────────────────────────────────

function createTrayIcon(): nativeImage {
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
        buf[i] = 255;   // R
        buf[i + 1] = 140; // G
        buf[i + 2] = 120; // B
        buf[i + 3] = 255; // A
      } else {
        buf[i + 3] = 0;  // transparent
      }
    }
  }

  return nativeImage.createFromBuffer(buf, { width: size, height: size });
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
      sandbox: false,
    },
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

  const devUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5174';

  // Try Vite dev server first; fall back to production build
  (async () => {
    try {
      const resp = await fetch(devUrl);
      if (resp.ok) {
        mainWindow!.loadURL(devUrl);
        return;
      }
    } catch {}
    mainWindow!.loadFile(join(__dirname, '../dist/index.html'));
  })();
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
  ipcMain.handle('store:get', (_e, key: string) => store.get(key));
  ipcMain.handle('store:set', (_e, key: string, value: any) => store.set(key, value));

  ipcMain.handle('tool:exec', async (_e, name: string, params: Record<string, any>) => {
    const { execTool } = await import('./tool-bridge');
    return execTool(name, params);
  });

  ipcMain.handle('tool:list', async () => {
    const { listTools } = await import('./tool-bridge');
    return listTools();
  });

  ipcMain.handle('device:status', () => getDeviceStatus());

  ipcMain.handle('app:autoLaunch', (_e, enabled?: boolean) => {
    if (typeof enabled === 'boolean') {
      store.set('autoLaunch', enabled);
      app.setLoginItemSettings({ openAtLogin: enabled });
    }
    return store.get('autoLaunch');
  });

  ipcMain.on('notification:show', (_e, title: string, body: string) => {
    if (Notification.isSupported()) {
      new Notification({ title, body }).show();
    }
  });
}

// ── App lifecycle ─────────────────────────────────────────────────────

app.whenReady().then(() => {
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
  globalShortcut.unregisterAll();
});
