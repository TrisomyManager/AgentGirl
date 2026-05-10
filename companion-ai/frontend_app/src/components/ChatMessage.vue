<template>
  <div class="message-wrapper" :class="message.role">
    <div v-if="message.role === 'assistant'" class="msg-avatar">
      <img
        src="https://placehold.co/36x36/e94560/FFF?text=暖"
        alt="小暖"
      />
    </div>

    <div class="message-content">
      <!-- User: WeChat-style voice bubble -->
      <div
        v-if="message.role === 'user' && message.type === 'voice'"
        class="message-bubble user voice-bubble"
      >
        <div class="voice-row">
          <button
            type="button"
            class="voice-play-btn"
            :disabled="!message.audioUrl"
            :title="message.audioUrl ? '播放录音' : '录音已失效（刷新后无法重播）'"
            @click="toggleUserVoicePlay"
          >
            {{ userVoicePlaying ? '⏹' : '▶' }}
          </button>
          <div class="voice-wave" aria-hidden="true">
            <span v-for="i in 4" :key="i" class="bar" />
          </div>
          <span class="voice-duration">{{ voiceDurationLabel }}</span>
        </div>
        <div class="voice-sub">
          <span v-if="message.transcriptStatus === 'pending'" class="voice-status pending">识别中…</span>
          <template v-else-if="message.transcriptStatus === 'done' && message.transcript">
            <span class="voice-transcript-label">转文字：</span>
            <span class="voice-transcript-text">{{ message.transcript }}</span>
          </template>
          <span v-else class="voice-status failed">{{ userVoiceFailureLabel }}</span>
        </div>
      </div>

      <!-- User: plain text -->
      <div
        v-else-if="message.role === 'user'"
        class="message-bubble user"
      >
        <div class="message-text">
          <span v-html="renderedUserText"></span>
        </div>
      </div>

      <!-- Assistant -->
      <div v-else class="message-bubble assistant">
        <div
          v-if="message.isTyping && !message.content"
          class="typing-indicator"
        >
          <span></span>
          <span></span>
          <span></span>
        </div>
        <div v-else class="message-text">
          <span v-html="renderedContent"></span>
          <span v-if="message.isTyping" class="streaming-cursor" aria-hidden="true">▍</span>
        </div>
        <div v-if="assistantVoiceVisible" class="assistant-voice-row">
          <template v-if="message.voiceStatus === 'pending'">
            <span class="voice-pending" aria-live="polite">语音合成中…</span>
          </template>
          <template v-else-if="message.voiceStatus === 'failed' || message.voiceSynthesisError">
            <span class="synthesis-err-title">语音合成失败</span>
            <span v-if="shortSynthErr" class="synthesis-err-detail">{{ shortSynthErr }}</span>
          </template>
          <template v-else-if="message.voiceUrl">
            <button
              type="button"
              class="assistant-voice-btn"
              :disabled="message.voiceStatus === 'playing'"
              @click="playAssistantVoice"
            >
              <span class="assistant-voice-icon" aria-hidden="true">🔊</span>
              {{ message.voiceStatus === 'playing' ? '播放中…' : '播放语音' }}
            </button>
            <span v-if="assistantTtsSec" class="tts-dur-label">{{ assistantTtsSec }}″</span>
            <span v-if="message.ttsErrorMessage" class="tts-err">{{ ttsErrorShort }}</span>
          </template>
        </div>
      </div>

      <div class="message-meta" :class="message.role">
        <span v-if="message.role === 'assistant'" class="sender-name">小暖</span>
        <span class="timestamp">{{ formattedTime }}</span>
        <span v-if="message.actionText" class="action-tag">{{ message.actionText }}</span>
      </div>
    </div>

    <div v-if="message.role === 'user'" class="msg-avatar user">
      <img
        src="https://placehold.co/36x36/3b82f6/FFF?text=U"
        alt="User"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import type { AssistantVoicePlaybackEvent, ChatMessage } from '../composables/useChat';
import type { useVoice } from '../composables/useVoice';

const props = defineProps<{
  message: ChatMessage;
  voice: ReturnType<typeof useVoice>;
}>();

const emit = defineEmits<{
  assistantVoicePlayback: [AssistantVoicePlaybackEvent];
}>();

const userVoicePlaying = ref(false);
let userAudio: HTMLAudioElement | null = null;

const formattedTime = computed(() => {
  const date = new Date(props.message.timestamp);
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
});

const voiceDurationLabel = computed(() => {
  const ms = props.message.durationMs ?? 0;
  const sec = Math.max(1, Math.round(ms / 1000));
  return `${sec}″`;
});

const userVoiceFailureLabel = computed(() => {
  if (props.message.transcriptStatus !== 'failed') return '';
  const c = props.message.asrErrorCode;
  switch (c) {
    case 'recording_too_short':
      return '录音太短';
    case 'audio_convert_failed':
      return '格式转换失败';
    case 'asr_empty':
      return '未识别（无有效语音）';
    case 'asr_upstream_error':
    case 'asr_config':
    case 'voice_endpoint_404':
    case 'voice_endpoint_503':
    case 'network':
    case 'unknown':
    default:
      return '未识别';
  }
});

const assistantVoiceVisible = computed(() => {
  if (props.message.role !== 'assistant') return false;
  return (
    props.message.voiceStatus === 'pending' ||
    !!props.message.voiceUrl ||
    props.message.voiceStatus === 'failed' ||
    !!props.message.voiceSynthesisError
  );
});

const assistantTtsSec = computed(() => {
  const ms = props.message.voiceDurationMs;
  if (ms === undefined || ms === null || Number.isNaN(ms)) return '';
  return String(Math.max(1, Math.round(ms / 1000)));
});

const shortSynthErr = computed(() => {
  const s = props.message.voiceSynthesisError || '';
  if (!s) return '';
  return s.length > 120 ? `${s.slice(0, 120)}…` : s;
});

const ttsErrorShort = computed(() => {
  const m = props.message.ttsErrorMessage || '';
  if (m.includes('404')) return '语音文件不存在';
  return '播放失败';
});

function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/`(.+?)`/g, '<code>$1</code>');
  html = html.replace(/\n/g, '<br>');

  return html;
}

const renderedContent = computed(() => {
  if (props.message.isTyping && !props.message.content) return '';
  return renderMarkdown(props.message.content || '');
});

const renderedUserText = computed(() => renderMarkdown(props.message.content || ''));

function stopUserVoice() {
  if (userAudio) {
    userAudio.pause();
    userAudio.currentTime = 0;
    userAudio = null;
  }
  userVoicePlaying.value = false;
}

function toggleUserVoicePlay() {
  const url = props.message.audioUrl;
  if (!url) return;

  if (userVoicePlaying.value && userAudio) {
    stopUserVoice();
    return;
  }

  stopUserVoice();
  userAudio = new Audio(url);
  userAudio.onended = () => {
    userAudio = null;
    userVoicePlaying.value = false;
  };
  userAudio.onerror = () => {
    userAudio = null;
    userVoicePlaying.value = false;
  };
  userAudio
    .play()
    .then(() => {
      userVoicePlaying.value = true;
    })
    .catch(() => {
      userVoicePlaying.value = false;
    });
}

async function playAssistantVoice() {
  const u = props.message.voiceUrl;
  if (!u || props.message.voiceStatus === 'playing') return;
  emit('assistantVoicePlayback', { id: props.message.id, phase: 'start' });
  try {
    await props.voice.playAudio(u, { force: true });
    emit('assistantVoicePlayback', { id: props.message.id, phase: 'end' });
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    emit('assistantVoicePlayback', { id: props.message.id, phase: 'error', error: err });
  }
}

watch(
  () => props.message.audioUrl,
  () => {
    stopUserVoice();
  },
);

onUnmounted(() => {
  stopUserVoice();
  if (props.message.audioUrl?.startsWith('blob:')) {
    URL.revokeObjectURL(props.message.audioUrl);
  }
});
</script>

<style scoped>
.message-wrapper {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  animation: fadeInUp 0.3s ease;
}

.message-wrapper.user {
  flex-direction: row-reverse;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.msg-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
}

.msg-avatar img {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
}

.msg-avatar.user img {
  border: 2px solid rgba(59, 130, 246, 0.5);
}

.message-content {
  display: flex;
  flex-direction: column;
  max-width: 70%;
}

.message-wrapper.user .message-content {
  align-items: flex-end;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.message-bubble.assistant {
  background: #1a1a2e;
  color: #e2e8f0;
  border-bottom-left-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.message-bubble.user {
  background: linear-gradient(135deg, #e94560, #d63050);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message-bubble.user.voice-bubble {
  min-width: 200px;
  max-width: 280px;
}

.voice-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.voice-play-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.voice-play-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.voice-wave {
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 22px;
}

.voice-wave .bar {
  width: 3px;
  background: rgba(255, 255, 255, 0.55);
  border-radius: 2px;
  animation: barPulse 0.9s ease-in-out infinite;
}

.voice-wave .bar:nth-child(1) {
  height: 40%;
  animation-delay: 0s;
}
.voice-wave .bar:nth-child(2) {
  height: 70%;
  animation-delay: 0.1s;
}
.voice-wave .bar:nth-child(3) {
  height: 100%;
  animation-delay: 0.2s;
}
.voice-wave .bar:nth-child(4) {
  height: 55%;
  animation-delay: 0.3s;
}

@keyframes barPulse {
  0%,
  100% {
    opacity: 0.5;
    transform: scaleY(0.85);
  }
  50% {
    opacity: 1;
    transform: scaleY(1);
  }
}

.voice-duration {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  opacity: 0.95;
}

.voice-sub {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.45;
  opacity: 0.92;
}

.voice-status.pending {
  color: rgba(255, 255, 255, 0.85);
}

.voice-status.failed {
  color: rgba(254, 226, 226, 0.95);
}

.voice-transcript-label {
  opacity: 0.75;
}

.voice-transcript-text {
  font-weight: 500;
}

.assistant-voice-row {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.voice-pending {
  font-size: 12px;
  color: #94a3b8;
}

.synthesis-err-title {
  font-size: 12px;
  font-weight: 600;
  color: #fca5a5;
}

.synthesis-err-detail {
  font-size: 11px;
  color: #cbd5e1;
  opacity: 0.85;
  max-width: 100%;
}

.assistant-voice-btn {
  border: 1px solid rgba(233, 69, 96, 0.35);
  background: rgba(233, 69, 96, 0.12);
  color: #fda4af;
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 999px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.assistant-voice-btn:hover:not(:disabled) {
  background: rgba(233, 69, 96, 0.22);
}

.assistant-voice-btn:disabled {
  opacity: 0.75;
  cursor: default;
}

.assistant-voice-icon {
  font-size: 14px;
}

.tts-dur-label {
  font-size: 11px;
  color: #94a3b8;
}

.tts-err {
  font-size: 11px;
  color: #fca5a5;
}

.message-text {
  white-space: pre-wrap;
}

.message-text :deep(strong) {
  font-weight: 600;
}

.message-text :deep(code) {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 13px;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: #64748b;
}

.message-meta.user {
  justify-content: flex-end;
}

.sender-name {
  color: #e94560;
  font-weight: 500;
}

.action-tag {
  background: rgba(233, 69, 96, 0.15);
  color: #e94560;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10px;
}

.streaming-cursor {
  display: inline-block;
  margin-left: 1px;
  color: #e94560;
  animation: cursorBlink 1s steps(1) infinite;
  font-weight: 700;
}

@keyframes cursorBlink {
  50% {
    opacity: 0;
  }
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #64748b;
  border-radius: 50%;
  animation: typingBounce 1.4s ease-in-out infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typingBounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-6px);
  }
}
</style>
