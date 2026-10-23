import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('petAPI', {
  status: () => ipcRenderer.invoke('pet:status'),
  move: (dx: number, dy: number) => ipcRenderer.invoke('pet:move', dx, dy),
  dragEnd: () => ipcRenderer.invoke('pet:drag-end'),
  menu: () => ipcRenderer.invoke('pet:menu'),
  onPack: (callback: (pack: unknown) => void) => {
    const listener = (_event: unknown, pack: unknown) => callback(pack);
    ipcRenderer.on('pet:pack', listener);
    return () => ipcRenderer.removeListener('pet:pack', listener);
  },
  onBubble: (callback: (bubble: unknown) => void) => {
    const listener = (_event: unknown, bubble: unknown) => callback(bubble);
    ipcRenderer.on('pet:bubble', listener);
    return () => ipcRenderer.removeListener('pet:bubble', listener);
  },
});
