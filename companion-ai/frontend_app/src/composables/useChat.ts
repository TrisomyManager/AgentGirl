import { computed, ref } from 'vue';
import { useApi, type TurnResponse } from './useApi';
import { useVoice } from './useVoice';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  emotion?: string;
  voiceUrl?: string;
  actionText?: string;
  isTyping?: boolean;
}

const STORAGE_KEY = 'companion_chat_history';
const STORAGE_SESSION_KEY = 'companion_session_id';
const STORAGE_USER_KEY = 'companion_user_name';

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function loadHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return JSON.parse(raw) as ChatMessage[];
    }
  } catch {
    // ignore malformed local data
  }
  return [];
}

function saveHistory(messages: ChatMessage[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch {
    // ignore storage errors
  }
}

export function useChat() {
  const messages = ref<ChatMessage[]>(loadHistory());
  const isTyping = ref(false);
  const currentEmotion = ref('neutral');
  const currentAction = ref('');
  const sessionId = ref(localStorage.getItem(STORAGE_SESSION_KEY) || generateSessionId());
  const userName = ref(localStorage.getItem(STORAGE_USER_KEY) || '用户');
  const userId = 'user_001';

  const { isLoading, error, serverAvailable, sendTurn, transcribeVoice, clearError, checkServer } = useApi();
  const voice = useVoice();

  if (!localStorage.getItem(STORAGE_SESSION_KEY)) {
    localStorage.setItem(STORAGE_SESSION_KEY, sessionId.value);
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
    saveHistory(messages.value);
  }

  function updateUserName(name: string) {
    userName.value = name || '用户';
    localStorage.setItem(STORAGE_USER_KEY, userName.value);
  }

  function clearHistory() {
    messages.value = [];
    localStorage.removeItem(STORAGE_KEY);
    sessionId.value = generateSessionId();
    localStorage.setItem(STORAGE_SESSION_KEY, sessionId.value);
    currentEmotion.value = 'neutral';
    currentAction.value = '';
  }

  async function sendMessage(content: string) {
    const trimmed = content.trim();
    if (!trimmed) {
      return;
    }

    clearError();
    addMessage({
      id: generateId(),
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    });

    isTyping.value = true;
    const resp = await sendTurn({
      session_id: sessionId.value,
      user: {
        user_id: userId,
        display_name: userName.value,
      },
      user_message: trimmed,
      platform: 'app',
    });
    isTyping.value = false;

    if (resp) {
      handleTurnResponse(resp);
    }
  }

  function handleTurnResponse(resp: TurnResponse) {
    if (resp.emotion?.primary) {
      currentEmotion.value = resp.emotion.primary;
    }

    if (resp.action_sequence?.frames?.length) {
      const firstAction = resp.action_sequence.frames[0].action_type;
      currentAction.value = firstAction;
      setTimeout(() => {
        currentAction.value = '';
      }, resp.action_sequence.total_duration_ms || 3000);
    }

    const assistantMsg: ChatMessage = {
      id: resp.turn_id || generateId(),
      role: 'assistant',
      content: resp.assistant_message || '（无回复）',
      timestamp: Date.now(),
      emotion: resp.emotion?.primary,
      voiceUrl: resp.voice_url,
      actionText: resp.action_sequence?.frames?.[0]?.action_type
        ? actionLabelMap[resp.action_sequence.frames[0].action_type]
        : undefined,
    };
    addMessage(assistantMsg);

    if (resp.voice_url && voice.autoPlayEnabled.value) {
      voice.playAudio(resp.voice_url).catch(() => {
        // ignore playback failures
      });
    }
  }

  async function sendVoiceMessage(audioBlob: Blob) {
    clearError();
    isTyping.value = true;
    const text = await transcribeVoice(audioBlob);
    isTyping.value = false;

    if (text) {
      await sendMessage(text);
      return;
    }

    error.value = '未能识别语音内容，请重试。';
  }

  voice.onStopRecording.value = async (blob: Blob) => {
    await sendVoiceMessage(blob);
  };

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
    sendVoiceMessage,
    updateUserName,
    clearHistory,
    clearError,
    checkServer,
  };
}
