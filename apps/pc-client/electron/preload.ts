import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  getStoreValue: (key: string) => ipcRenderer.invoke('store:get', key),
  setStoreValue: (key: string, value: any) => ipcRenderer.invoke('store:set', key, value),

  onNotification: (callback: (data: any) => void) => {
    ipcRenderer.on('notification:received', (_event, data) => callback(data));
  },

  showNotification: (title: string, body: string) => {
    ipcRenderer.send('notification:show', title, body);
  },

  minimizeToTray: () => ipcRenderer.send('window:minimize-to-tray'),

  onTrayCommand: (callback: (cmd: string) => void) => {
    ipcRenderer.on('tray:command', (_event, cmd) => callback(cmd));
  },

  toolExec: (name: string, params: Record<string, any>) =>
    ipcRenderer.invoke('tool:exec', name, params),

  toolList: () => ipcRenderer.invoke('tool:list'),

  getDeviceStatus: () => ipcRenderer.invoke('device:status'),
});
