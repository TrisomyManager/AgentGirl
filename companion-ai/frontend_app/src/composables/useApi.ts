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

  async function getLlmConfig(): Promise<{ provider: string; api_key_set: boolean; base_url: string; model: string } | null> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/settings/llm`);
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  async function saveLlmConfig(cfg: { provider: string; api_key: string; base_url: string; model: string }): Promise<boolean> {
    try {
      const resp = await fetch(`${ORCHESTRATOR_URL}/orchestrator/settings/llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      });
      return resp.ok;
    } catch {
      return false;
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

  function clearError() {
    error.value = null;
  }

  return {
    isLoading,
    error,
    serverAvailable,
    checkServer,
    sendTurn,
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
    clearError,
  };
}
