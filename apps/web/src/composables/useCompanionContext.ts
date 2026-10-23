import { onMounted, onUnmounted, watch, type Ref } from 'vue';
import { companionRequest, desktopBridge } from './desktopBridge';

/** Only starts metadata polling after both backend and per-user consent are enabled. */
export function useCompanionContext(userId: string, busy: Ref<boolean>) {
  let policy: { enabled: boolean; desktop_enabled: boolean } | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let pending = false;
  let stopped = false;
  async function sample() {
    const bridge = desktopBridge();
    if (stopped || pending || !bridge || !policy?.enabled || !policy.desktop_enabled) return;
    pending = true;
    try {
      const [context, device] = await Promise.all([bridge.companionContext(), bridge.getDeviceStatus()]);
      if (!context.available || stopped || !policy?.enabled || !policy.desktop_enabled) return;
      await companionRequest('/actions/proactive/context', 'POST', {
        user_id: userId, device_id: device.deviceId, foreground_app: context.foreground_app,
        idle_seconds: context.idle_seconds, locked: context.locked, fullscreen: context.fullscreen,
        interacting: context.interacting, busy: busy.value,
      });
    } catch { /* Missing backend / OS support never interrupts the chat UI. */ }
    finally { pending = false; }
  }
  async function reload() {
    if (timer) clearInterval(timer);
    timer = null;
    policy = null;
    if (!desktopBridge() || stopped) return;
    try {
      const result = await companionRequest(`/actions/proactive/preferences?user_id=${encodeURIComponent(userId)}`);
      policy = result.desktop_context_active ? result.policy : null;
      if (!stopped && policy?.enabled && policy.desktop_enabled) {
        void sample(); timer = setInterval(() => void sample(), 8000);
      }
    } catch { /* Explicit settings save or next mount retries. */ }
  }
  onMounted(() => {
    void reload(); window.addEventListener('companion-preferences-changed', reload);
  });
  watch(busy, () => void sample());
  onUnmounted(() => {
    stopped = true; policy = null;
    if (timer) clearInterval(timer);
    window.removeEventListener('companion-preferences-changed', reload);
  });
}
