import { onMounted, onUnmounted, ref } from 'vue';

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') ||
  'http://127.0.0.1:8000';

const PUSH_SINCE_KEY_PREFIX = 'companion_push_since_';
const SEEN_REMINDERS_KEY_PREFIX = 'companion_seen_reminders_';
const MAX_SEEN_REMINDERS = 50;

export interface ReminderFiredPayload {
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

  // ── Persistent state ─────────────────────────────────────────────
  const sinceStorageKey = `${PUSH_SINCE_KEY_PREFIX}${userId}`;
  const seenStorageKey = `${SEEN_REMINDERS_KEY_PREFIX}${userId}`;

  let sinceSeq = 0;
  let hasPersistedSeq = false;
  let seenReminderIds = new Set<string>();

  try {
    const storedSince = localStorage.getItem(sinceStorageKey);
    if (storedSince !== null) {
      sinceSeq = Number(storedSince);
      hasPersistedSeq = true;
    }
    const storedSeen = localStorage.getItem(seenStorageKey);
    if (storedSeen) {
      seenReminderIds = new Set(JSON.parse(storedSeen));
    }
  } catch { /* localStorage unavailable */ }

  function _persistSince() {
    try { localStorage.setItem(sinceStorageKey, String(sinceSeq)); } catch { /* ignore */ }
  }

  function _persistSeen() {
    try {
      const arr = Array.from(seenReminderIds).slice(-MAX_SEEN_REMINDERS);
      localStorage.setItem(seenStorageKey, JSON.stringify(arr));
    } catch { /* ignore */ }
  }

  // ── Deduped reminder toast ───────────────────────────────────────
  function showReminderToast(payload: ReminderFiredPayload) {
    const id = payload.id;
    if (id && seenReminderIds.has(id)) return;
    if (id) seenReminderIds.add(id);
    _persistSeen();
    lastReminder.value = payload;
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
          const proactive: ProactiveEvent = {
            kind: eventName,
            payload: parsed,
            receivedAt: Date.now(),
          };
          events.value.push(proactive);
          if (events.value.length > 64) events.value.splice(0, events.value.length - 64);
          if (eventName === 'reminder_fired') {
            showReminderToast(parsed as ReminderFiredPayload);
          }
          if (eventName === 'proactive_message') {
            options?.onProactiveMessage?.(parsed as ProactiveMessagePayload);
          }
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
    if (stop) return;
    try {
      const resp = await fetch(
        `${API_BASE_URL}/actions/push/poll?since=${sinceSeq}&user_id=${encodeURIComponent(userId)}`,
      );
      if (!resp.ok) return;
      const body = (await resp.json()) as {
        latest_seq?: number;
        events?: Array<{ kind: string; payload: unknown }>;
      };

      const latest = typeof body.latest_seq === 'number' ? body.latest_seq : sinceSeq;

      // First poll after page load: sync seq without replaying history.
      if (!hasPersistedSeq) {
        sinceSeq = latest;
        _persistSince();
        hasPersistedSeq = true;
        return;
      }

      for (const ev of body.events ?? []) {
        if (!ev.payload || typeof ev.payload !== 'object') continue;
        if (ev.kind === 'reminder_fired') {
          showReminderToast(ev.payload as ReminderFiredPayload);
        } else if (ev.kind === 'proactive_message') {
          options?.onProactiveMessage?.(ev.payload as ProactiveMessagePayload);
        }
      }

      sinceSeq = latest;
      _persistSince();
    } catch {
      /* ignore — SSE may still work */
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
