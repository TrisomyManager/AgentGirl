import { onMounted, onUnmounted, ref } from 'vue';

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') ||
  'http://127.0.0.1:8000';

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

/**
 * Subscribes to /actions/push (SSE) for proactive events such as
 * `reminder_fired`. Mirrors the same hand-rolled SSE parser used by
 * useApi.streamTurn so we don't pull in a new dep just for this.
 */
export function useProactivePush() {
  const events = ref<ProactiveEvent[]>([]);
  const lastReminder = ref<ReminderFiredPayload | null>(null);
  const connected = ref(false);
  const error = ref<string | null>(null);

  let abort: AbortController | null = null;
  let stop = false;
  let reconnectTimer: number | null = null;
  let pollTimer: number | null = null;
  let sinceSeq = 0;
  const seenReminderIds = new Set<string>();

  function rememberReminderPayload(payload: ReminderFiredPayload | Record<string, unknown>) {
    const id = (payload as ReminderFiredPayload).id;
    if (id) {
      if (seenReminderIds.has(id)) return;
      seenReminderIds.add(id);
    }
    lastReminder.value = payload as ReminderFiredPayload;
  }

  async function readStream(controller: AbortController) {
    try {
      const resp = await fetch(`${API_BASE_URL}/actions/push`, {
        method: 'GET',
        headers: { Accept: 'text/event-stream' },
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }
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
          if (eventName === 'hello') continue;
          if (dataLines.length === 0) continue;

          let parsed: any = null;
          try {
            parsed = JSON.parse(dataLines.join('\n'));
          } catch {
            parsed = { raw: dataLines.join('\n') };
          }
          const event: ProactiveEvent = {
            kind: eventName,
            payload: parsed,
            receivedAt: Date.now(),
          };
          events.value.push(event);
          if (events.value.length > 64) events.value.splice(0, events.value.length - 64);
          if (eventName === 'reminder_fired') {
            rememberReminderPayload(parsed as ReminderFiredPayload);
          }
        }
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      const msg = err instanceof Error ? err.message : String(err);
      connected.value = false;
      error.value = msg;
    }
  }

  async function pollOnce() {
    if (stop) return;
    try {
      const resp = await fetch(`${API_BASE_URL}/actions/push/poll?since=${sinceSeq}`);
      if (!resp.ok) return;
      const body = (await resp.json()) as { latest_seq?: number; events?: Array<{ kind: string; payload: unknown }> };
      if (typeof body.latest_seq === 'number') {
        sinceSeq = body.latest_seq;
      }
      for (const ev of body.events ?? []) {
        if (ev.kind !== 'reminder_fired' || !ev.payload || typeof ev.payload !== 'object') continue;
        rememberReminderPayload(ev.payload as ReminderFiredPayload);
      }
    } catch {
      /* ignore — SSE may still work */
    }
  }

  async function connect() {
    if (stop) return;
    abort?.abort();
    abort = new AbortController();
    try {
      await readStream(abort);
    } finally {
      connected.value = false;
      if (!stop) {
        // Auto-reconnect with a small backoff. Browser will not retry
        // GET fetch streams automatically, so we have to.
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
