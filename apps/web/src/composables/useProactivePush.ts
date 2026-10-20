import { onMounted, onUnmounted, ref } from 'vue';
import { apiFetch as fetch } from './accessSession';

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') ||
  'http://127.0.0.1:8000';

const PUSH_SINCE_KEY_PREFIX = 'companion_push_since_v2_';
const SEEN_REMINDERS_KEY_PREFIX = 'companion_seen_reminders_';
const MAX_SEEN_REMINDERS = 2048;

export interface ReminderFiredPayload {
  event_id?: string;
  id: string;
  user_id: string;
  session_id: string | null;
  text: string;
  fire_at: string;
}

export interface ProactiveEvent {
  kind: string;
  payload: any;
  receivedAt: number;
}

export interface ProactiveMessagePayload {
  event_id?: string;
  id: string;
  user_id: string;
  message: string;
  trigger_type: string;
  timestamp: string;
  emotion?: string | null;
}

export interface ProactivePushOptions {
  /** Called when a proactive_message event arrives via SSE or poll. */
  onProactiveMessage?: (payload: ProactiveMessagePayload) => void;
}

export function pushEventIdentity(kind: string, payload: Record<string, unknown>): string {
  if (typeof payload.event_id === 'string') return payload.event_id;
  return `${kind}:${payload.id || ''}:${payload.fire_at || ''}`;
}

/**
 * Subscribes to /actions/push (SSE) for proactive events such as
 * `reminder_fired` and `proactive_message`. Since-seq and per-user
 * seen-reminder IDs are persisted to localStorage so that page
 * refreshes never replay historical toasts.
 *
 * @param userId - scopes subscriptions + persistence to this user
 * @param options - optional callbacks for specific event kinds
 */
export function useProactivePush(userId: string, options?: ProactivePushOptions) {
  const events = ref<ProactiveEvent[]>([]);
  const lastReminder = ref<ReminderFiredPayload | null>(null);
  const connected = ref(false);
  const error = ref<string | null>(null);

  let abort: AbortController | null = null;
  let stop = false;
  let reconnectTimer: number | null = null;
  let pollTimer: number | null = null;
  let polling = false;

  // ── Persistent state ─────────────────────────────────────────────
  const sinceStorageKey = `${PUSH_SINCE_KEY_PREFIX}${userId}`;
  const seenStorageKey = `${SEEN_REMINDERS_KEY_PREFIX}${userId}`;

  let sinceSeq = 0;
  let hasPersistedSeq = false;
  let seenReminderIds = new Set<string>();

  try {
    const storedSince = localStorage.getItem(sinceStorageKey);
    if (storedSince !== null) {
      const parsed = Number(storedSince);
      if (Number.isSafeInteger(parsed) && parsed >= 0) {
        sinceSeq = parsed;
        hasPersistedSeq = true;
      }
    }
    const storedSeen = localStorage.getItem(seenStorageKey);
    if (storedSeen) {
      const parsed = JSON.parse(storedSeen);
      if (Array.isArray(parsed)) seenReminderIds = new Set(parsed.filter((id): id is string => typeof id === 'string'));
    }
  } catch { /* localStorage unavailable */ }

  function _persistSince() {
    try { localStorage.setItem(sinceStorageKey, String(sinceSeq)); } catch { /* ignore */ }
  }

  function _persistSeen() {
    seenReminderIds = new Set(Array.from(seenReminderIds).slice(-MAX_SEEN_REMINDERS));
    try {
      const arr = Array.from(seenReminderIds).slice(-MAX_SEEN_REMINDERS);
      localStorage.setItem(seenStorageKey, JSON.stringify(arr));
    } catch { /* ignore */ }
  }

  // ── Deduped reminder toast ───────────────────────────────────────
  function showReminderToast(payload: ReminderFiredPayload) {
    lastReminder.value = payload;
  }

  function deliver(kind: string, payload: any) {
    if (stop || !payload || typeof payload !== 'object') return;
    const id = pushEventIdentity(kind, payload);
    if (seenReminderIds.has(id)) return;
    if (kind === 'reminder_fired') showReminderToast(payload as ReminderFiredPayload);
    if (kind === 'proactive_message') options?.onProactiveMessage?.(payload as ProactiveMessagePayload);
    const desktop = (window as Window & { electronAPI?: {
      showNotification?: (title: string, body: string) => void;
      showBackgroundNotification?: (title: string, body: string) => void;
    } }).electronAPI;
    const notify = desktop?.showBackgroundNotification ||
      ((document.visibilityState === 'hidden' || !document.hasFocus()) ? desktop?.showNotification : undefined);
    if (notify) {
      const body = kind === 'reminder_fired' ? payload.text : kind === 'proactive_message' ? payload.message : '';
      if (body) notify(kind === 'reminder_fired' ? '小暖提醒你' : '小暖', body);
    }
    events.value.push({ kind, payload, receivedAt: Date.now() });
    if (events.value.length > 64) events.value.splice(0, events.value.length - 64);
    seenReminderIds.add(id);
    _persistSeen();
  }

  // ── SSE stream ───────────────────────────────────────────────────
  async function readStream(controller: AbortController) {
    try {
      const resp = await fetch(
        `${API_BASE_URL}/actions/push?user_id=${encodeURIComponent(userId)}`,
        {
          method: 'GET',
          headers: { Accept: 'text/event-stream' },
          signal: controller.signal,
        },
      );
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      connected.value = true;
      error.value = null;

      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buf = '';

      while (!stop) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        let sepIdx;
        while ((sepIdx = buf.indexOf('\n\n')) !== -1) {
          const frame = buf.slice(0, sepIdx);
          buf = buf.slice(sepIdx + 2);
          let eventName = 'message';
          const dataLines: string[] = [];
          for (const rawLine of frame.split('\n')) {
            const line = rawLine.trimEnd();
            if (!line) continue;
            if (line.startsWith('event:')) eventName = line.slice(6).trim();
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
          }
          if (eventName === 'hello' || eventName === 'ping') continue;
          if (dataLines.length === 0) continue;

          let parsed: any = null;
          try {
            parsed = JSON.parse(dataLines.join('\n'));
          } catch {
            parsed = { raw: dataLines.join('\n') };
          }
          deliver(eventName, parsed);
        }
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      connected.value = false;
      error.value = err instanceof Error ? err.message : String(err);
    }
  }

  // ── Poll (SSE fallback) ──────────────────────────────────────────
  async function pollOnce() {
    if (stop || polling) return;
    polling = true;
    try {
      let hasMore = false;
      do {
      const resp = await fetch(
        `${API_BASE_URL}/actions/push/poll?since=${sinceSeq}&user_id=${encodeURIComponent(userId)}`,
      );
      if (!resp.ok) return;
      const body = (await resp.json()) as {
        latest_seq?: number;
        durable?: boolean;
        has_more?: boolean;
        events?: Array<{ kind: string; payload: unknown }>;
      };

      const latest = typeof body.latest_seq === 'number' ? body.latest_seq : sinceSeq;

      if (stop) return;
      // Legacy memory-only servers cannot replay across restarts.
      if (!hasPersistedSeq && !body.durable) {
        sinceSeq = latest;
        _persistSince();
        hasPersistedSeq = true;
        return;
      }

      for (const ev of body.events ?? []) {
        if (!ev.payload || typeof ev.payload !== 'object') continue;
        deliver(ev.kind, ev.payload);
      }

      sinceSeq = latest;
      hasPersistedSeq = true;
      _persistSince();
      hasMore = body.has_more === true;
      } while (hasMore && !stop);
    } catch {
      /* ignore — SSE may still work */
    } finally {
      polling = false;
    }
  }

  // ── Connection lifecycle ────────────────────────────────────────
  async function connect() {
    if (stop) return;
    abort?.abort();
    abort = new AbortController();
    try {
      await readStream(abort);
    } finally {
      connected.value = false;
      if (!stop) {
        reconnectTimer = window.setTimeout(() => connect(), 3000);
      }
    }
  }

  function dismissLastReminder() {
    lastReminder.value = null;
  }

  onMounted(() => {
    stop = false;
    void connect();
    pollTimer = window.setInterval(() => void pollOnce(), 2500);
    void pollOnce();
  });

  onUnmounted(() => {
    stop = true;
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    if (pollTimer) window.clearInterval(pollTimer);
    abort?.abort();
  });

  return {
    events,
    lastReminder,
    connected,
    error,
    dismissLastReminder,
  };
}
