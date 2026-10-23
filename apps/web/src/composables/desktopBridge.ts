export interface PetClip { id: string; name: string; group: string; url: string }
export interface PetPack { name: string; width: number; height: number; bodyBox: number[]; clips: PetClip[] }
export interface DesktopBridge {
  petStatus(): Promise<{ enabled: boolean; clickThrough: boolean; pack: PetPack | null }>;
  petChoosePack(): Promise<PetPack | null>;
  petSetEnabled(enabled: boolean): Promise<unknown>;
  petSetClickThrough(enabled: boolean): Promise<unknown>;
  petBubble(text: string, emotion?: string): Promise<unknown>;
  companionContext(): Promise<{ available: boolean; foreground_app: string; fullscreen: boolean;
    idle_seconds: number; locked: boolean; interacting: boolean }>;
  getDeviceStatus(): Promise<{ deviceId: string; userId: string }>;
}

export function desktopBridge(): DesktopBridge | undefined {
  return (window as unknown as { electronAPI?: DesktopBridge }).electronAPI;
}

export const COMPANION_API = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '')
  || 'http://127.0.0.1:8000';

export async function companionRequest(path: string, method = 'GET', body?: unknown) {
  const response = await fetch(`${COMPANION_API}${path}`, { method,
    headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败（${response.status}）`);
  }
  return response.json();
}
