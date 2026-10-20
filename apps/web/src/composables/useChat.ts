import { computed, getCurrentScope, onScopeDispose, ref, watch } from 'vue';
import { currentUserId, userStorageKey } from './accessSession';
import { useApi, type TranscribeVoiceResult, type TurnResponse, type VoiceSegment } from './useApi';
import { useVoice } from './useVoice';
import { useToolStatus } from './useToolStatus';
import { createSegmentedPlayback } from './segmentedPlayback';
import type { AvatarTimeline } from '../../../../packages/avatar-runtime/src';

type AsrFailureCode = Extract<TranscribeVoiceResult, { ok: false }>['code'];

export type MessageType = 'text' | 'voice';
export type TranscriptStatus = 'pending' | 'done' | 'failed';
export type AssistantVoiceStatus = 'pending' | 'ready' | 'failed' | 'playing';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  type: MessageType;
  content: string;
  timestamp: number;
  emotion?: string;
  expressionEmoji?: string;
  quietlyAcknowledged?: boolean;
  imageUrls?: string[];
  imageCount?: number;
  /** Local blob URL for user-recorded audio (session-only). */
  audioUrl?: string;
  durationMs?: number;
  transcript?: string;
  transcriptStatus?: TranscriptStatus;
  /** Assistant TTS URL from backend (relative or absolute). */
  voiceUrl?: string;
  voiceSegments?: VoiceSegment[];
  avatarTimeline?: AvatarTimeline;
  /** Duration of assistant TTS audio from backend (ms). */
  voiceDurationMs?: number;
  /** Assistant-side voice lifecycle (TTS + playback). */
  voiceStatus?: AssistantVoiceStatus;
  /** Backend TTS failure detail when synthesis fails. */
  voiceSynthesisError?: string;
  actionText?: string;
  isTyping?: boolean;
  /** When ASR fails, echo API error code for bubble copy. */
  asrErrorCode?: AsrFailureCode;
  /** Client-side playback / load failure (distinct from voiceSynthesisError). */
  ttsErrorMessage?: string;
  /** True while waiting for TTS after streaming when user asked for voice reply. */
  expectVoiceReply?: boolean;
}

export type AssistantVoicePlaybackEvent = {
  id: string;
  phase: 'start' | 'end' | 'error' | 'stop';
  error?: string;
};

export interface SendMessageOptions {
  hasVoiceInput?: boolean;
  requestVoiceReply?: boolean;
  voiceDurationMs?: number;
  imageUrls?: string[];
}

const STORAGE_KEY = 'companion_chat_history';
/** Exported for realtime voice WebSocket identity (must match chat session). */
export const COMPANION_SESSION_STORAGE_KEY = 'companion_session_id';
const STORAGE_SESSION_KEY = COMPANION_SESSION_STORAGE_KEY;
const STORAGE_USER_KEY = 'companion_user_name';
/** Default user id for orchestrator / memory (same as chat turns). */
export const COMPANION_DEFAULT_USER_ID = 'user_001';

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function normalizeStoredMessage(raw: Record<string, unknown>): ChatMessage {
  const role = raw.role === 'assistant' ? 'assistant' : 'user';
  const type: MessageType = raw.type === 'voice' ? 'voice' : 'text';
  const transcriptStatus = raw.transcriptStatus;
  const ts: TranscriptStatus | undefined =
    transcriptStatus === 'pending' || transcriptStatus === 'done' || transcriptStatus === 'failed'
      ? transcriptStatus
      : undefined;
  const audioUrl = typeof raw.audioUrl === 'string' ? raw.audioUrl : undefined;
  let finalStatus = ts;
  let asrCode = typeof raw.asrErrorCode === 'string' ? raw.asrErrorCode : undefined;
  if (type === 'voice' && finalStatus === 'pending' && !audioUrl) {
    finalStatus = 'failed';
    asrCode = asrCode || 'unknown';
  }
  return {
    id: String(raw.id ?? generateId()),
    role,
    type,
    content: typeof raw.content === 'string' ? raw.content : '',
    timestamp: typeof raw.timestamp === 'number' ? raw.timestamp : Date.now(),
    emotion: typeof raw.emotion === 'string' ? raw.emotion : undefined,
    expressionEmoji: typeof raw.expressionEmoji === 'string' ? raw.expressionEmoji : undefined,
    quietlyAcknowledged: raw.quietlyAcknowledged === true,
    imageCount: typeof raw.imageCount === 'number' ? Math.min(3, Math.max(0, raw.imageCount)) : undefined,
    audioUrl,
    durationMs: typeof raw.durationMs === 'number' ? raw.durationMs : undefined,
    transcript: typeof raw.transcript === 'string' ? raw.transcript : undefined,
    transcriptStatus: finalStatus,
    voiceUrl: typeof raw.voiceUrl === 'string' ? raw.voiceUrl : undefined,
    avatarTimeline: raw.avatarTimeline as AvatarTimeline | undefined,
    voiceSegments: Array.isArray(raw.voiceSegments) ? raw.voiceSegments.filter(
      (segment): segment is VoiceSegment => !!segment && typeof segment === 'object' &&
        typeof segment.audio_url === 'string' && Number.isInteger(segment.seq),
    ).slice(0, 256) : undefined,
    voiceDurationMs: typeof raw.voiceDurationMs === 'number' ? raw.voiceDurationMs : undefined,
    voiceSynthesisError:
      typeof raw.voiceSynthesisError === 'string' ? raw.voiceSynthesisError : undefined,
    voiceStatus: normalizeLoadedVoiceStatus(
      raw.voiceStatus,
      raw.voiceUrl,
      raw.voiceSynthesisError,
    ),
    actionText: typeof raw.actionText === 'string' ? raw.actionText : undefined,
    isTyping: Boolean(raw.isTyping),
    asrErrorCode: asrCode as ChatMessage['asrErrorCode'],
    ttsErrorMessage: typeof raw.ttsErrorMessage === 'string' ? raw.ttsErrorMessage : undefined,
    expectVoiceReply: Boolean(raw.expectVoiceReply),
  };
}

function normalizeLoadedVoiceStatus(
  raw: unknown,
  voiceUrl: unknown,
  synthesisErr: unknown,
): AssistantVoiceStatus | undefined {
  if (raw === 'pending' || raw === 'ready' || raw === 'failed' || raw === 'playing') {
    if (raw === 'playing') return 'ready';
    return raw;
  }
  if (typeof synthesisErr === 'string' && synthesisErr) return 'failed';
  if (typeof voiceUrl === 'string' && voiceUrl) return 'ready';
  return undefined;
}

function loadHistory(storageKey = STORAGE_KEY): ChatMessage[] {
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw) {
      const parsed = JSON.parse(raw) as unknown;
      if (!Array.isArray(parsed)) return [];
      return parsed.map((x) => normalizeStoredMessage(x as Record<string, unknown>));
    }
  } catch {
    // ignore malformed local data
  }
  return [];
}

function sanitizeForStorage(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((m) => {
    const c = { ...m };
    delete c.imageUrls; // Images remain in this session only; never fill browser history with private originals.
    if (c.audioUrl?.startsWith('blob:')) {
      delete c.audioUrl;
    }
    if (c.voiceStatus === 'playing') {
      c.voiceStatus = 'ready';
    }
    delete c.expectVoiceReply;
    return c;
  });
}

function saveHistory(messages: ChatMessage[], storageKey = STORAGE_KEY) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(sanitizeForStorage(messages)));
  } catch {
    // ignore storage errors
  }
}

function bannerTextForAsrFailure(r: Extract<TranscribeVoiceResult, { ok: false }>): string {
  switch (r.code) {
    case 'recording_too_short':
      return r.message;
    case 'audio_convert_failed':
      return r.message;
    case 'asr_empty':
      return r.message;
    case 'asr_upstream_error':
      return r.message;
    case 'asr_config':
      return r.message;
    case 'voice_endpoint_404':
    case 'voice_endpoint_503':
      return r.message;
    case 'network':
      return r.message;
    default:
      return r.message || '语音识别失败，请重试。';
  }
}

export function useChat() {
  let workVersion = 0;
  const userId = currentUserId();
  const historyKey = userStorageKey(STORAGE_KEY);
  const sessionKey = userStorageKey(STORAGE_SESSION_KEY);
  const nameKey = userStorageKey(STORAGE_USER_KEY);
  const messages = ref<ChatMessage[]>(loadHistory(historyKey));
  const isTyping = ref(false);
  const currentEmotion = ref([...messages.value].reverse().find(message => message.role === 'assistant' && message.emotion)?.emotion || 'neutral');
  const currentAction = ref('');
  const sessionId = ref(localStorage.getItem(sessionKey) || generateSessionId());
  const userName = ref(localStorage.getItem(nameKey) || '用户');

  const {
    isLoading,
    error,
    serverAvailable,
    streamTurn,
    transcribeVoice,
    clearError,
    checkServer,
    getPersonaEmotion,
  } = useApi();
  const voice = useVoice();
  const toolStatus = useToolStatus();
  let turnAbort: AbortController | null = null;
  let segmentMessageId = '';
  let playingTimeline: AvatarTimeline | undefined;
  const segmentedPlayback = createSegmentedPlayback({
    play: url => voice.playAudio(url, { avatarTimeline: playingTimeline }),
    stop: () => voice.stopAudio(), allowed: () => voice.autoPlayEnabled.value,
    onStart: seq => {
      updateMessage(segmentMessageId, { voiceStatus: 'playing' });
      const segment = messages.value.find(message => message.id === segmentMessageId)?.voiceSegments?.find(item => item.seq === seq);
      playingTimeline = segment?.avatar_timeline;
    },
    onEnd: () => updateMessage(segmentMessageId, { voiceStatus: 'ready' }),
    onError: message => updateMessage(segmentMessageId, { ttsErrorMessage: message }),
  });
  watch(voice.autoPlayEnabled, enabled => {
    if (!enabled) {
      segmentedPlayback.stop();
      if (segmentMessageId) updateMessage(segmentMessageId, { voiceStatus: 'ready' });
    }
  });

  async function refreshEmotion() {
    const originalSession = sessionId.value;
    const originalLength = messages.value.length;
    const previous = currentEmotion.value;
    const persisted = await getPersonaEmotion(userId);
    if (persisted && !isTyping.value && sessionId.value === originalSession && messages.value.length === originalLength && currentEmotion.value === previous) {
      currentEmotion.value = persisted;
    }
  }

  if (!localStorage.getItem(sessionKey)) {
    localStorage.setItem(sessionKey, sessionId.value);
  }

  const emotionLabelMap: Record<string, string> = {
    neutral: '平静',
    happy: '开心',
    sad: '难过',
    angry: '生气',
    surprised: '惊讶',
    fearful: '害怕',
    disgusted: '厌恶',
    affectionate: '温柔',
    concerned: '关心',
    excited: '兴奋',
    calm: '平静',
  };

  const actionLabelMap: Record<string, string> = {
    idle: '待机中',
    talk: '正在说话',
    listen: '正在倾听',
    react_happy: '开心回应',
    react_sad: '难过回应',
    react_surprised: '惊讶回应',
    react_thinking: '正在思考',
    gesture_wave: '挥手',
    gesture_nod: '点头',
    gesture_head_tilt: '歪头',
  };

  const emotionLabel = computed(() => {
    return emotionLabelMap[currentEmotion.value] || currentEmotion.value || '平静';
  });

  const actionLabel = computed(() => {
    if (!currentAction.value) {
      return '';
    }
    return actionLabelMap[currentAction.value] || currentAction.value;
  });

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg);
    saveHistory(messages.value, historyKey);
  }

  /** Inject an assistant message into the chat (used for proactive messages). */
  function injectAssistantMessage(content: string, extra?: { emotion?: string; actionText?: string }) {
    const msg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      type: 'text',
      content,
      timestamp: Date.now(),
      emotion: extra?.emotion,
      actionText: extra?.actionText,
    };
    addMessage(msg);
  }

  function updateUserName(name: string) {
    userName.value = name || '用户';
    localStorage.setItem(nameKey, userName.value);
  }

  function clearHistory() {
    stopCurrentWork();
    isTyping.value = false;
    for (const m of messages.value) {
      if (m.audioUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(m.audioUrl);
      }
    }
    messages.value = [];
    localStorage.removeItem(historyKey);
    sessionId.value = generateSessionId();
    localStorage.setItem(sessionKey, sessionId.value);
    currentEmotion.value = 'neutral';
    currentAction.value = '';
  }

  function stopCurrentWork() {
    workVersion += 1;
    turnAbort?.abort();
    segmentedPlayback.stop();
    voice.stopAudio();
    voice.discardRecording();
    isTyping.value = false;
    if (_appendSaveTimer) { clearTimeout(_appendSaveTimer); _appendSaveTimer = null; }
  }

  function findMessageIndex(id: string): number {
    return messages.value.findIndex((m) => m.id === id);
  }

  function updateMessage(id: string, patch: Partial<ChatMessage>) {
    const idx = findMessageIndex(id);
    if (idx === -1) return;
    const next = messages.value.slice();
    next[idx] = { ...next[idx], ...patch };
    messages.value = next;
    saveHistory(messages.value, historyKey);
  }

  let _appendSaveTimer: ReturnType<typeof setTimeout> | null = null;

  function appendToMessage(id: string, chunk: string) {
    const idx = findMessageIndex(id);
    if (idx === -1) return;
    const prev = messages.value[idx];
    const next = messages.value.slice();
    next[idx] = { ...prev, content: (prev.content || '') + chunk };
    messages.value = next;
    if (_appendSaveTimer) clearTimeout(_appendSaveTimer);
    _appendSaveTimer = setTimeout(() => {
      saveHistory(messages.value, historyKey);
      _appendSaveTimer = null;
    }, 200);
  }

  async function runStreamedTurn(userMessage: string, options: SendMessageOptions = {}): Promise<void> {
    turnAbort?.abort();
    const controller = new AbortController();
    turnAbort = controller;
    segmentedPlayback.stop();
    toolStatus.resetForNewTurn();
    const wantsVoiceReply = options.requestVoiceReply ?? voice.autoPlayEnabled.value;
    const userMessageId = [...messages.value].reverse().find(message => message.role === 'user')?.id;
    const turnReq = {
      session_id: sessionId.value,
      user: {
        user_id: userId,
        display_name: userName.value,
      },
      user_message: userMessage,
      platform: 'app',
      has_voice: options.hasVoiceInput ?? false,
      request_voice_reply: wantsVoiceReply,
      supports_segmented_voice: true,
      has_image: !!options.imageUrls?.length,
      image_urls: options.imageUrls,
      voice_duration_ms:
        options.voiceDurationMs !== undefined ? Math.round(options.voiceDurationMs) : undefined,
    };

    const assistantId = generateId();
    addMessage({
      id: assistantId,
      role: 'assistant',
      type: 'text',
      content: '',
      timestamp: Date.now(),
      isTyping: true,
      expectVoiceReply: wantsVoiceReply,
      voiceStatus: wantsVoiceReply ? 'pending' : undefined,
    });

    segmentMessageId = assistantId;
    segmentedPlayback.start();

    isTyping.value = true;
    const resp = await streamTurn(turnReq, {
      onToken: (text) => {
        if (controller.signal.aborted) return;
        appendToMessage(assistantId, text);
      },
      onMeta: (meta) => {
        if (controller.signal.aborted) return;
        if (meta?.emotion?.primary) {
          currentEmotion.value = meta.emotion.primary;
        }
      },
      onToolStatus: (payload) => {
        if (controller.signal.aborted) return;
        if (payload.status === 'pending') {
          toolStatus.startTool(payload.tool_name, payload.message);
        } else {
          toolStatus.endTool(payload.status === 'success', payload.message);
        }
      },
      onVoiceSegment: segment => {
        if (controller.signal.aborted) return;
        const prior = messages.value.find(message => message.id === assistantId)?.voiceSegments || [];
        if (!prior.some(item => item.seq === segment.seq)) {
          updateMessage(assistantId, { voiceSegments: [...prior, segment].sort((a, b) => a.seq - b.seq) });
          segmentedPlayback.put(segment.seq, segment.audio_url);
        }
      },
      onVoiceSegmentError: event => {
        if (controller.signal.aborted) return;
        updateMessage(assistantId, { voiceSynthesisError: event.error });
        segmentedPlayback.put(event.seq, null);
      },
      onVoiceDone: event => { if (!controller.signal.aborted) segmentedPlayback.finish(event.segments); },
      onError: () => {
        if (controller.signal.aborted) return;
        /* error ref set in useApi */
        toolStatus.endTool(false, '流式传输出错');
      },
    }, controller.signal);
    if (controller.signal.aborted || turnAbort !== controller) return;
    isTyping.value = false;

    if (resp) {
      finalizeStreamedMessage(assistantId, resp, userMessageId);
      if (toolStatus.isExecuting.value) {
        const taskFailed = resp.task && !['completed', 'awaiting_input'].includes(resp.task.status);
        toolStatus.endTool(!taskFailed, taskFailed ? resp.task!.message : undefined);
      }
    } else {
      toolStatus.endTool(false, '连接中断');
      const idx = findMessageIndex(assistantId);
      if (idx !== -1) {
        const partial = messages.value[idx].content;
        if (!partial) {
          updateMessage(assistantId, {
            content: '（连接中断，请稍后再试）',
            isTyping: false,
            expectVoiceReply: false,
            voiceStatus: undefined,
          });
        } else {
          updateMessage(assistantId, {
            isTyping: false,
            expectVoiceReply: false,
            voiceStatus: undefined,
          });
        }
      }
    }
  }

  function finalizeStreamedMessage(assistantId: string, resp: TurnResponse, userMessageId?: string) {
    if (resp.emotion?.primary) {
      currentEmotion.value = resp.emotion.primary;
    }

    if (resp.reply_suppressed && !resp.error) {
      messages.value = messages.value.filter(message => message.id !== assistantId);
      if (userMessageId) updateMessage(userMessageId, { quietlyAcknowledged: true });
      saveHistory(messages.value, historyKey);
      return;
    }

    if (resp.action_sequence?.frames?.length) {
      const firstAction = resp.action_sequence.frames[0].action_type;
      currentAction.value = firstAction;
      setTimeout(() => {
        currentAction.value = '';
      }, resp.action_sequence.total_duration_ms || 3000);
    }

    const idx = findMessageIndex(assistantId);
    const expectV = messages.value[idx]?.expectVoiceReply;

    const finalContent =
      resp.assistant_message ||
      messages.value[idx]?.content ||
      '（无回复）';

    const voicePatch: Partial<ChatMessage> = {
      content: finalContent,
      avatarTimeline: resp.avatar_timeline || undefined,
      isTyping: false,
      emotion: resp.emotion?.primary,
      expressionEmoji: resp.expression_emoji || undefined,
      ttsErrorMessage: undefined,
      expectVoiceReply: false,
      actionText: resp.action_sequence?.frames?.[0]?.action_type
        ? actionLabelMap[resp.action_sequence.frames[0].action_type]
        : undefined,
    };

    const rawUrl = resp.voice_url;
    const voiceUrl =
      typeof rawUrl === 'string' && rawUrl.trim().length > 0 ? rawUrl.trim() : '';

    const rawSynthErr = resp.voice_error;
    const backendSynthErr =
      typeof rawSynthErr === 'string' && rawSynthErr.trim().length > 0
        ? rawSynthErr.trim()
        : '';

    if (resp.voice_mode === 'segmented') {
      const segments = resp.voice_segments || messages.value[idx]?.voiceSegments || [];
      voicePatch.voiceSegments = segments;
      voicePatch.voiceUrl = undefined;
      voicePatch.voiceDurationMs = resp.voice_duration_ms;
      voicePatch.voiceSynthesisError = backendSynthErr || undefined;
      voicePatch.voiceStatus = segments.length ? (voice.isPlaying.value ? 'playing' : 'ready') : 'failed';
    } else if (voiceUrl) {
      voicePatch.voiceUrl = voiceUrl;
      voicePatch.voiceDurationMs =
        resp.voice_duration_ms !== undefined && resp.voice_duration_ms !== null
          ? Number(resp.voice_duration_ms)
          : undefined;
      voicePatch.voiceSynthesisError = undefined;
      voicePatch.voiceStatus = 'ready';
    } else if (expectV) {
      const synthMsg =
        backendSynthErr || '后端未返回 voice_url，可能未执行语音合成';
      voicePatch.voiceUrl = undefined;
      voicePatch.voiceDurationMs = undefined;
      voicePatch.voiceSynthesisError = synthMsg;
      voicePatch.voiceStatus = 'failed';
      error.value = `语音合成失败：${synthMsg}`;
    } else {
      voicePatch.voiceUrl = undefined;
      voicePatch.voiceDurationMs = undefined;
      voicePatch.voiceSynthesisError = undefined;
      voicePatch.voiceStatus = undefined;
    }

    updateMessage(assistantId, voicePatch);

    if (voiceUrl && voice.autoPlayEnabled.value) {
      void (async () => {
        updateMessage(assistantId, { voiceStatus: 'playing', ttsErrorMessage: undefined });
        try {
          await voice.playAudio(voiceUrl, { avatarTimeline: resp.avatar_timeline || undefined });
          updateMessage(assistantId, { voiceStatus: 'ready' });
        } catch (e) {
          const detail =
            e instanceof Error
              ? e.message
              : 'TTS 播放失败：请检查语音合成配置或音频地址是否可访问。';
          const msg = `音频生成了但播放失败：${detail}`;
          updateMessage(assistantId, {
            voiceStatus: 'ready',
            ttsErrorMessage: msg,
          });
          error.value = msg;
        }
      })();
    }
  }

  function handleAssistantVoicePlayback(ev: AssistantVoicePlaybackEvent) {
    if (ev.phase === 'stop') {
      segmentedPlayback.stop();
      updateMessage(ev.id, { voiceStatus: 'ready' });
      return;
    }
    if (ev.phase === 'start') {
      segmentedPlayback.stop();
      updateMessage(ev.id, { voiceStatus: 'playing', ttsErrorMessage: undefined });
      return;
    }
    if (ev.phase === 'end') {
      updateMessage(ev.id, { voiceStatus: 'ready' });
      return;
    }
    const detail = ev.error || '未知错误';
    const msg = `音频生成了但播放失败：${detail}`;
    updateMessage(ev.id, { voiceStatus: 'ready', ttsErrorMessage: msg });
    error.value = msg;
  }

  async function sendMessage(content: string, options: SendMessageOptions = {}) {
    const trimmed = content.trim() || (options.imageUrls?.length ? '请看看这些图片。' : '');
    if (!trimmed) {
      return;
    }

    clearError();
    // Bound retained previews while keeping a visible attachment receipt in older messages.
    for (const message of messages.value.filter(message => message.imageUrls?.length).slice(0, -2)) {
      delete message.imageUrls;
    }
    addMessage({
      id: generateId(),
      role: 'user',
      type: 'text',
      content: trimmed,
      imageUrls: options.imageUrls?.length ? [...options.imageUrls] : undefined,
      imageCount: options.imageUrls?.length || undefined,
      timestamp: Date.now(),
    });

    await runStreamedTurn(trimmed, options);
  }

  async function handleVoiceRecordingStopped(blob: Blob, durationMs: number) {
    const version = workVersion;
    const audioUrl = URL.createObjectURL(blob);
    const voiceId = generateId();
    clearError();

    addMessage({
      id: voiceId,
      role: 'user',
      type: 'voice',
      content: '',
      timestamp: Date.now(),
      audioUrl,
      durationMs,
      transcriptStatus: 'pending',
    });

    const asr = await transcribeVoice(blob, { reportGlobalError: false });
    if (version !== workVersion) return;

    if (!asr.ok) {
      const code = asr.code;
      updateMessage(voiceId, {
        transcriptStatus: 'failed',
        asrErrorCode: code,
      });
      error.value = bannerTextForAsrFailure(asr);
      return;
    }

    updateMessage(voiceId, {
      transcript: asr.text,
      transcriptStatus: 'done',
    });

    clearError();
    await runStreamedTurn(asr.text, {
      hasVoiceInput: true,
      requestVoiceReply: true,
      voiceDurationMs: durationMs,
    });
  }

  voice.onStopRecording.value = async (blob: Blob, durationMs: number) => {
    await handleVoiceRecordingStopped(blob, durationMs);
  };

  if (getCurrentScope()) onScopeDispose(() => {
    stopCurrentWork();
    for (const message of messages.value) if (message.audioUrl?.startsWith('blob:')) URL.revokeObjectURL(message.audioUrl);
  });

  return {
    messages,
    isTyping,
    isLoading,
    error,
    currentEmotion,
    emotionLabel,
    actionLabel,
    sessionId,
    userName,
    userId,
    serverAvailable,
    voice,
    sendMessage,
    updateUserName,
    clearHistory,
    stopCurrentWork,
    clearError,
    checkServer,
    refreshEmotion,
    handleAssistantVoicePlayback,
    toolStatus,
    injectAssistantMessage,
  };
}
