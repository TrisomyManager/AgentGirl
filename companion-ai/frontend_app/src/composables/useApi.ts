import { ref } from 'vue';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') || 'http://127.0.0.1:8000';
const ORCHESTRATOR_URL = API_BASE_URL;
const VOICE_URL = API_BASE_URL;

/** Resolve relative API paths (e.g. /static/voice/x.mp3) against the backend base URL. */
export function absoluteApiUrl(path: string): string {
  const p = (path || '').trim();
  if (!p) return '';
  if (/^https?:\/\//i.test(p)) return p;
  const base = API_BASE_URL.replace(/\/$/, '');
  return p.startsWith('/') ? base + p : `${base}/${p}`;
}

function voiceHttpHint(status: number): string {
  if (status === 404) {
    return '语音接口未挂载（404）。请确认已设置 COMPANION_ENABLE_VOICE=true 并重启后端。';
  }
  if (status === 503) {
    return '语音模块未启用（503）。请使用 COMPANION_ENABLE_VOICE=true 或运行 scripts/start_lite_server.py --voice。';
  }
  return '';
}

export type VoiceErrorDetail = { message: string; code?: string };

async function readVoiceErrorDetail(resp: Response): Promise<VoiceErrorDetail> {
  try {
    const j = (await resp.json()) as { detail?: unknown };
    const d = j.detail;
    if (d && typeof d === 'object' && !Array.isArray(d) && 'message' in d) {
      const o = d as { message?: string; code?: string };
      return { message: String(o.message || '请求失败'), code: o.code };
    }
    if (typeof d === 'string') return { message: d };
    if (Array.isArray(d)) {
      const message = d
        .map((x) => (typeof x === 'object' && x !== null && 'msg' in x ? String((x as { msg?: string }).msg) : String(x)))
        .filter(Boolean)
        .join('；');
      return { message: message || '请求失败' };
    }
  } catch {
    /* ignore */
  }
  return { message: '' };
}

async function readJsonDetail(resp: Response): Promise<string> {
  const { message } = await readVoiceErrorDetail(resp);
  return message;
}

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
  voice_duration_ms?: number;
  /** Populated when TTS was attempted but failed; text reply is still valid. */
  voice_error?: string;
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

const MIN_VOICE_RECORDING_BYTES = 2800;

export type TranscribeVoiceResult =
  | { ok: true; text: string }
  | {
      ok: false;
      code:
        | 'recording_too_short'
        | 'audio_convert_failed'
        | 'voice_endpoint_404'
        | 'voice_endpoint_503'
        | 'asr_empty'
        | 'asr_upstream_error'
        | 'asr_config'
        | 'network'
        | 'unknown';
      message: string;
    };

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

export interface ToolStatusPayload {
  tool_name: string;
  status: 'pending' | 'success' | 'error';
  message?: string;
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
    onToolStatus?: (payload: ToolStatusPayload) => void;
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
          case 'tool_status':
            if (parsed && typeof parsed === 'object' && 'tool_name' in parsed) {
              handlers.onToolStatus?.(parsed as ToolStatusPayload);
            }
            break;
          case 'error':
            handlers.onError?.(parsed.error || 'unknown stream error');
            break;
          case 'done':
            if (parsed && typeof parsed === 'object' && 'assistant_message' in parsed) {
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

  async function transcribeVoice(
    audioBlob: Blob,
    opts: { reportGlobalError?: boolean } = {},
  ): Promise<TranscribeVoiceResult> {
    const reportGlobal = opts.reportGlobalError !== false;

    const setGlobal = (msg: string | null) => {
      if (reportGlobal) {
        error.value = msg;
      }
    };

    if (audioBlob.size < MIN_VOICE_RECORDING_BYTES) {
      const message = '录音太短，请按住稍长一点时间再松手。';
      setGlobal(message);
      return { ok: false, code: 'recording_too_short', message };
    }

    let uploadBlob: Blob;
    let filename: string;
    try {
      const { blobToWav16kMono } = await import('./audioCodec');
      uploadBlob = await blobToWav16kMono(audioBlob);
      filename = 'recording.wav';
    } catch (convErr) {
      const message = `音频格式转换失败：${convErr instanceof Error ? convErr.message : String(convErr)}。请重试或更换浏览器。`;
      setGlobal(message);
      return { ok: false, code: 'audio_convert_failed', message };
    }

    const formData = new FormData();
    formData.append('audio', uploadBlob, filename);
    try {
      const resp = await fetch(`${VOICE_URL}/voice/transcribe`, {
        method: 'POST',
        body: formData,
      });
      if (resp.status === 404) {
        const message =
          (await readJsonDetail(resp)) ||
          voiceHttpHint(404) ||
          '语音转写接口不存在（404）。请确认已启用语音模块并重启后端。';
        setGlobal(message);
        return { ok: false, code: 'voice_endpoint_404', message };
      }
      if (resp.status === 503) {
        const message = (await readJsonDetail(resp)) || voiceHttpHint(503) || '语音服务不可用（503）。';
        setGlobal(message);
        return { ok: false, code: 'voice_endpoint_503', message };
      }
      if (!resp.ok) {
        const { message: detail, code } = await readVoiceErrorDetail(resp);
        const hint = voiceHttpHint(resp.status);
        const base = detail || hint || `HTTP ${resp.status}`;
        if (resp.status === 502 || code === 'asr_upstream_error') {
          const message = base.startsWith('ASR') ? base : `ASR 上游错误：${base}`;
          setGlobal(message);
          return { ok: false, code: 'asr_upstream_error', message };
        }
        if (resp.status === 400 && (code === 'asr_config_missing' || code === 'asr_audio_too_short')) {
          const message = detail || base;
          setGlobal(message);
          return { ok: false, code: code === 'asr_audio_too_short' ? 'recording_too_short' : 'asr_config', message };
        }
        const message = base;
        setGlobal(message);
        return { ok: false, code: 'unknown', message };
      }
      const data: TranscribeResponse = await resp.json();
      const text = (data.text || '').trim();
      if (!text) {
        const message = '识别结果为空：未检测到有效语音内容，请大声清晰地说完后重试。';
        setGlobal(message);
        return { ok: false, code: 'asr_empty', message };
      }
      if (reportGlobal) {
        error.value = null;
      }
      return { ok: true, text };
    } catch (err) {
      const message = `网络或请求失败：${err instanceof Error ? err.message : String(err)}`;
      setGlobal(message);
      return { ok: false, code: 'network', message };
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
        const detail = await readJsonDetail(resp);
        const hint = voiceHttpHint(resp.status);
        throw new Error(detail || hint || `HTTP ${resp.status}`);
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

  async function testLlmConfig(): Promise<{
    ok: boolean;
    provider: string;
    model: string;
    base_url: string;
    latency_ms: number;
    sample_reply: string;
    error: string;
  } | null> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/settings/llm/test`, {
        method: 'POST',
      });
      if (!resp.ok) {
        try {
          const err = (await resp.json()) as { detail?: string };
          return {
            ok: false,
            provider: '',
            model: '',
            base_url: '',
            latency_ms: 0,
            sample_reply: '',
            error: err.detail || `HTTP ${resp.status}`,
          };
        } catch {
          return {
            ok: false,
            provider: '',
            model: '',
            base_url: '',
            latency_ms: 0,
            sample_reply: '',
            error: `HTTP ${resp.status}`,
          };
        }
      }
      return await resp.json();
    } catch (e) {
      return {
        ok: false,
        provider: '',
        model: '',
        base_url: '',
        latency_ms: 0,
        sample_reply: '',
        error: (e as Error).message || '请求失败（后端未运行？）',
      };
    }
  }

  async function testVoiceConfig(): Promise<{
    asr_ok: boolean;
    asr_provider: string;
    asr_model: string;
    asr_message: string;
    tts_ok: boolean;
    tts_provider: string;
    tts_model: string;
    tts_voice: string;
    tts_latency_ms: number;
    tts_audio_url: string;
    tts_duration_ms: number;
    tts_error: string;
  } | null> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/settings/voice/test`, {
        method: 'POST',
      });
      if (!resp.ok) {
        const detail = await readJsonDetail(resp);
        const hint = voiceHttpHint(resp.status);
        const errText = detail || hint || `请求失败（HTTP ${resp.status}）`;
        return {
          asr_ok: false,
          asr_provider: '',
          asr_model: '',
          asr_message: errText,
          tts_ok: false,
          tts_provider: '',
          tts_model: '',
          tts_voice: '',
          tts_latency_ms: 0,
          tts_audio_url: '',
          tts_duration_ms: 0,
          tts_error: errText,
        };
      }
      return await resp.json();
    } catch (e) {
      const msg = e instanceof Error ? e.message : '网络错误';
      return {
        asr_ok: false,
        asr_provider: '',
        asr_model: '',
        asr_message: `请求失败：${msg}`,
        tts_ok: false,
        tts_provider: '',
        tts_model: '',
        tts_voice: '',
        tts_latency_ms: 0,
        tts_audio_url: '',
        tts_duration_ms: 0,
        tts_error: `请求失败：${msg}（后端是否已启动？）`,
      };
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
    testLlmConfig,
    getVoiceConfig,
    saveVoiceConfig,
    testVoiceConfig,
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
recallMemory,
    deleteMemory,
    deleteAllMemories,
    listReminders,
    cancelReminder,
    listActions,
    clearError,
  };
}
