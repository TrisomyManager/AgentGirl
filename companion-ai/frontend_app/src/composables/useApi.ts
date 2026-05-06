import { ref } from 'vue';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') || 'http://127.0.0.1:8000';
const ORCHESTRATOR_URL = API_BASE_URL;
const VOICE_URL = API_BASE_URL;

export interface TurnRequest {
  session_id: string;
  user: {
    user_id: string;
    display_name: string;
  };
  user_message: string;
  platform: string;
  has_voice?: boolean;
  request_voice_reply?: boolean;
  voice_duration_ms?: number;
}

export interface TurnResponse {
  turn_id: string;
  session_id: string;
  user_id: string;
  assistant_message: string;
  emotion?: {
    primary: string;
    intensity?: number;
    valence?: number;
    arousal?: number;
  } | null;
  voice_url?: string;
  action_sequence?: {
    sequence_id: string;
    turn_id: string;
    frames: Array<{
      frame_id: string;
      action_type: string;
      image_url?: string;
      lip_shape?: string;
      duration_ms: number;
      emotion: string;
    }>;
    total_duration_ms: number;
    tts_audio_url?: string;
  };
  timestamp?: string;
}

export interface TranscribeResponse {
  text: string;
  confidence?: number;
}

export interface SynthesizeRequest {
  text: string;
  voice_id?: string;
  emotion?: string;
}

export interface LlmConfigSnapshot {
  provider: string;
  api_key_set: boolean;
  base_url: string;
  model: string;
}

export function useApi() {
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const serverAvailable = ref<boolean | null>(null);

  async function checkServer(): Promise<boolean> {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      const resp = await fetch(`${ORCHESTRATOR_URL}/health`, {
        signal: controller.signal,
        method: 'GET',
      }).catch(() => null);
      clearTimeout(timeout);
      serverAvailable.value = resp !== null && resp.ok;
      return serverAvailable.value;
    } catch {
      serverAvailable.value = false;
      return false;
    }
  }

  async function sendTurn(req: TurnRequest): Promise<TurnResponse | null> {
    isLoading.value = true;
    error.value = null;
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${text || resp.statusText}`);
      }
      const data: TurnResponse = await resp.json();
      serverAvailable.value = true;
      return data;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      error.value = msg;
      if (msg.includes('fetch') || msg.includes('NetworkError')) {
        serverAvailable.value = false;
      }
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  // ── Streaming turn (SSE) ──
  // Maps the /orchestrator/turn/stream wire protocol onto a tiny per-event
  // callback API. Returns the final TurnResponse-shaped object (assembled
  // from the SSE 'done' event) or null on transport error.
  interface StreamHandlers {
    onMeta?: (meta: {
      intent?: string | null;
      intent_confidence?: number | null;
      emotion?: TurnResponse['emotion'];
      memory_entries_count?: number;
    }) => void;
    onToken?: (text: string) => void;
    onError?: (msg: string) => void;
  }

  async function streamTurn(
    req: TurnRequest,
    handlers: StreamHandlers = {},
  ): Promise<TurnResponse | null> {
    isLoading.value = true;
    error.value = null;
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/turn/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(req),
      });
      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${text || resp.statusText}`);
      }
      serverAvailable.value = true;

      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buf = '';
      let finalPayload: TurnResponse | null = null;

      const dispatchEvent = (eventName: string, dataLine: string) => {
        let parsed: any;
        try {
          parsed = JSON.parse(dataLine);
        } catch {
          parsed = { text: dataLine };
        }
        switch (eventName) {
          case 'meta':
            handlers.onMeta?.(parsed);
            break;
          case 'token':
            if (typeof parsed.text === 'string') handlers.onToken?.(parsed.text);
            break;
          case 'error':
            handlers.onError?.(parsed.error || 'unknown stream error');
            break;
          case 'done':
            if (parsed && typeof parsed === 'object' && parsed.assistant_message) {
              finalPayload = parsed as TurnResponse;
            }
            break;
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        // Split into SSE frames separated by a blank line.
        let sepIdx;
        while ((sepIdx = buf.indexOf('\n\n')) !== -1) {
          const frame = buf.slice(0, sepIdx);
          buf = buf.slice(sepIdx + 2);
          let eventName = 'message';
          const dataLines: string[] = [];
          for (const rawLine of frame.split('\n')) {
            const line = rawLine.trimEnd();
            if (!line) continue;
            if (line.startsWith('event:')) {
              eventName = line.slice('event:'.length).trim();
            } else if (line.startsWith('data:')) {
              dataLines.push(line.slice('data:'.length).trim());
            }
          }
          if (dataLines.length > 0) {
            dispatchEvent(eventName, dataLines.join('\n'));
          }
        }
      }

      return finalPayload;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      error.value = msg;
      if (msg.includes('fetch') || msg.includes('NetworkError')) {
        serverAvailable.value = false;
      }
      handlers.onError?.(msg);
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  async function transcribeVoice(audioBlob: Blob): Promise<string | null> {
    // DashScope Paraformer requires WAV 16kHz mono. Convert in-browser to a
    // safe format that all providers (Whisper / Paraformer / SenseVoice) accept.
    let uploadBlob = audioBlob;
    let filename = 'recording.webm';
    try {
      const { blobToWav16kMono } = await import('./audioCodec');
      uploadBlob = await blobToWav16kMono(audioBlob);
      filename = 'recording.wav';
    } catch (convErr) {
      console.warn('wav conversion failed, sending original blob:', convErr);
    }

    const formData = new FormData();
    formData.append('audio', uploadBlob, filename);
    try {
      const resp = await fetch(`${VOICE_URL}/voice/transcribe`, {
        method: 'POST',
        body: formData,
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data: TranscribeResponse = await resp.json();
      return data.text || null;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      error.value = `语音转文字失败: ${msg}`;
      return null;
    }
  }

  async function synthesizeVoice(req: SynthesizeRequest): Promise<string | null> {
    try {
      const resp = await fetch(`${VOICE_URL}/voice/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      return data.audio_url || data.url || null;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      error.value = `语音合成失败: ${msg}`;
      return null;
    }
  }

  async function getLlmConfig(): Promise<LlmConfigSnapshot | null> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/settings/llm`);
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  async function saveLlmConfig(cfg: {
    provider: string;
    api_key: string;
    base_url: string;
    model: string;
  }): Promise<{ ok: true; config: LlmConfigSnapshot } | { ok: false; detail?: string }> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/settings/llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      });
      if (resp.ok) {
        const config = (await resp.json()) as LlmConfigSnapshot;
        return { ok: true, config };
      }
      let detail: string | undefined;
      try {
        const err = (await resp.json()) as { detail?: string };
        if (typeof err.detail === 'string') detail = err.detail;
      } catch {
        /* ignore */
      }
      return { ok: false, detail };
    } catch {
      return { ok: false };
    }
  }

  async function getVoiceConfig(): Promise<{
    asr_api_key_set: boolean;
    asr_base_url: string;
    asr_model: string;
    tts_provider: string;
    tts_api_key_set: boolean;
    tts_base_url: string;
    tts_model: string;
    tts_voice_id: string;
  } | null> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/settings/voice`);
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  async function saveVoiceConfig(cfg: {
    asr_api_key: string;
    asr_base_url: string;
    asr_model: string;
    tts_provider: string;
    tts_api_key: string;
    tts_base_url: string;
    tts_model: string;
    tts_voice_id: string;
  }): Promise<boolean> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/settings/voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }

  // ── Memory API ──
  async function listMemories(userId: string, limit = 50, offset = 0, category?: string): Promise<any[] | null> {
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      if (category) params.set('category', category);
      const resp = await fetch(`${ORCHESTRATOR_URL}/memory/user/${encodeURIComponent(userId)}/list?${params}`);
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  async function getMemorySummary(userId: string): Promise<any | null> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/memory/user/${encodeURIComponent(userId)}/summary`);
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  async function recallMemory(userId: string, query: string, topK = 5): Promise<any | null> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/memory/recall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, query, top_k: topK, include_graph: false }),
      });
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  async function deleteMemory(memoryId: string): Promise<boolean> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/memory/${encodeURIComponent(memoryId)}`, { method: 'DELETE' });
      return resp.ok;
    } catch {
      return false;
    }
  }

  async function deleteAllMemories(userId: string): Promise<boolean> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/memory/user/${encodeURIComponent(userId)}/all`, { method: 'DELETE' });
      return resp.ok;
    } catch {
      return false;
    }
  }

  // ── Action executor / reminders ──
  async function listReminders(
    userId: string,
    opts: { includeFired?: boolean; includeCancelled?: boolean } = {},
  ): Promise<any[] | null> {
    try {
      const params = new URLSearchParams();
      if (opts.includeFired) params.set('include_fired', 'true');
      if (opts.includeCancelled) params.set('include_cancelled', 'true');
      const url = `${ORCHESTRATOR_URL}/actions/reminders/${encodeURIComponent(userId)}${params.toString() ? `?${params}` : ''}`;
      const resp = await fetch(url);
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  async function cancelReminder(reminderId: string, userId?: string): Promise<boolean> {
    try {
      const params = new URLSearchParams();
      if (userId) params.set('user_id', userId);
      const url = `${ORCHESTRATOR_URL}/actions/reminders/${encodeURIComponent(reminderId)}${params.toString() ? `?${params}` : ''}`;
      const resp = await fetch(url, { method: 'DELETE' });
      return resp.ok;
    } catch {
      return false;
    }
  }

  async function listActions(): Promise<any[] | null> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/actions/list`);
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  function clearError() {
    error.value = null;
  }

  return {
    isLoading,
    error,
    serverAvailable,
    checkServer,
    sendTurn,
    streamTurn,
    transcribeVoice,
    synthesizeVoice,
    getLlmConfig,
    saveLlmConfig,
    getVoiceConfig,
    saveVoiceConfig,
    listMemories,
    getMemorySummary,
    recallMemory,
    deleteMemory,
    deleteAllMemories,
    listReminders,
    cancelReminder,
    listActions,
    clearError,
  };
}
