/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

interface Window {
  electronAPI: {
    getStoreValue: (key: string) => Promise<any>;
    setStoreValue: (key: string, value: any) => Promise<void>;
    onNotification: (callback: (data: any) => void) => void;
    showNotification: (title: string, body: string) => void;
    minimizeToTray: () => void;
    onTrayCommand: (callback: (cmd: string) => void) => void;
    toolExec: (name: string, params: Record<string, any>) => Promise<any>;
    toolList: () => Promise<any[]>;
    getDeviceStatus: () => Promise<{
      deviceId: string; userId: string; deviceName: string;
      registered: boolean; running: boolean;
      capabilities: string[]; version: string;
    }>;
  };
}
