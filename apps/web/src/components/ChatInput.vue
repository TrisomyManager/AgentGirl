<template>
  <div class="chat-input-area">
    <div v-if="attachments.images.value.length" class="image-previews">
      <div v-for="(image, index) in attachments.images.value" :key="image.url" class="image-preview">
        <img :src="image.url" :alt="image.name" />
        <button type="button" :aria-label="`移除图片 ${index + 1}`" @click="attachments.images.value.splice(index, 1)">×</button>
      </div>
    </div>
    <p v-if="attachments.error.value" role="alert" class="image-error">{{ attachments.error.value }}</p>
    <div class="input-wrapper">
      <input ref="imageInput" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden @change="selectImages" />
      <button type="button" class="image-btn" aria-label="添加图片" title="添加图片（最多 3 张）"
        :disabled="isLoading || attachments.reading.value" @click="imageInput?.click()">＋</button>
      <button
        class="voice-btn"
        :class="{ recording: voice.isRecording.value }"
        @mousedown="startVoice"
        @mouseup="stopVoice"
        @mouseleave="stopVoice"
        @touchstart.prevent="startVoice"
        @touchend.prevent="stopVoice"
        title="按住录音"
      >
        <span v-if="voice.isRecording.value" class="recording-icon">
          <span class="ripple"></span>
          <span class="ripple delay"></span>
          <span class="mic">🎤</span>
        </span>
        <span v-else>🎤</span>
      </button>

      <div class="text-input-wrapper">
        <textarea
          ref="textareaRef"
          v-model="inputText"
          placeholder="输入消息...（Shift+Enter 换行）"
          rows="1"
          @keydown="handleKeydown"
          @input="autoResize"
        ></textarea>
      </div>

      <button
        class="send-btn"
        :disabled="!canSend || isLoading"
        @click="send"
      >
        <span v-if="isLoading" class="spinner"></span>
        <span v-else>→</span>
      </button>
    </div>

    <div v-if="voice.isRecording.value" class="recording-hint">
      正在录音 {{ voice.recordingDuration.value }}s… 松开结束
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import type { useVoice } from '../composables/useVoice';
import type { SendMessageOptions } from '../composables/useChat';
import { useImageAttachments } from '../composables/useImageAttachments';

const props = defineProps<{
  isLoading: boolean;
  voice: ReturnType<typeof useVoice>;
  fillText?: string;
}>();

const emit = defineEmits<{
  (e: 'send', text: string, options?: SendMessageOptions): void;
  (e: 'filled'): void;
}>();

const inputText = ref('');
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const imageInput = ref<HTMLInputElement | null>(null);
const attachments = useImageAttachments();

async function selectImages(event: Event) {
  const input = event.target as HTMLInputElement;
  await attachments.select(Array.from(input.files || []));
  input.value = '';
}

const canSend = computed(() => !attachments.reading.value && (inputText.value.trim().length > 0 || attachments.images.value.length > 0));

// When parent sets fillText prop, paste it into the input field and focus.
watch(
  () => props.fillText,
  (text) => {
    if (text) {
      inputText.value = text;
      nextTick(() => {
        autoResize();
        textareaRef.value?.focus();
      });
      emit('filled');
    }
  },
);

function autoResize() {
  nextTick(() => {
    const el = textareaRef.value;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  });
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}

function send() {
  const text = inputText.value.trim();
  if (!canSend.value || props.isLoading) return;
  emit('send', text, { imageUrls: attachments.images.value.map(image => image.url) });
  attachments.clear();
  inputText.value = '';
  nextTick(() => {
    const el = textareaRef.value;
    if (el) {
      el.style.height = 'auto';
    }
  });
}

function startVoice() {
  if (props.voice.isRecording.value) return;
  props.voice.startRecording().catch(() => {
    alert('无法访问麦克风，请检查权限设置');
  });
}

function stopVoice() {
  if (props.voice.isRecording.value) {
    props.voice.stopRecording();
  }
}
</script>

<style scoped>
.image-previews { display: flex; gap: 10px; margin-bottom: 10px; }
.image-preview { position: relative; }
.image-preview img { width: 72px; height: 72px; object-fit: cover; border-radius: 10px; }
.image-preview button { position: absolute; top: -5px; right: -5px; border: 0; border-radius: 50%; background: #b92846; color: white; cursor: pointer; width: 24px; height: 24px; }
.image-error { color: #fda4af; font-size: 12px; margin: 0 0 8px; }
.image-btn { flex-shrink: 0; width: 32px; height: 42px; border: 0; background: transparent; color: #cbd5e1; font-size: 26px; cursor: pointer; }
.image-btn:disabled { opacity: .4; cursor: not-allowed; }
.chat-input-area {
  padding: 14px 16px 16px;
  background: rgba(15, 20, 34, 0.92);
  backdrop-filter: blur(12px);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.03);
}

.voice-btn {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.08);
  color: #ccc;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s ease;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
}

.voice-btn:hover {
  background: rgba(233, 69, 96, 0.2);
  color: #e94560;
}

.voice-btn.recording {
  background: rgba(233, 69, 96, 0.3);
  color: #e94560;
}

.recording-icon {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.ripple {
  position: absolute;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 2px solid #e94560;
  animation: rippleOut 1.2s ease-out infinite;
}

.ripple.delay {
  animation-delay: 0.6s;
}

@keyframes rippleOut {
  0% {
    transform: scale(1);
    opacity: 0.6;
  }
  100% {
    transform: scale(2);
    opacity: 0;
  }
}

.mic {
  position: relative;
  z-index: 1;
}

.text-input-wrapper {
  flex: 1;
  min-width: 0;
  background: rgba(8, 12, 24, 0.52);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 8px 16px;
  transition: border-color 0.2s ease;
}

.text-input-wrapper:focus-within {
  border-color: rgba(233, 69, 96, 0.4);
}

.text-input-wrapper textarea {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  color: #e2e8f0;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  max-height: 120px;
  font-family: inherit;
}

.text-input-wrapper textarea::placeholder {
  color: #475569;
}

.send-btn {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #e94560, #d63050);
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 4px 15px rgba(233, 69, 96, 0.3);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.recording-hint {
  text-align: center;
  font-size: 12px;
  color: #e94560;
  margin-top: 8px;
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@media (max-width: 640px) {
  .chat-input-area {
    padding: 10px 10px 12px;
  }

  .input-wrapper {
    gap: 8px;
    padding: 8px;
    border-radius: 18px;
  }

  .voice-btn,
  .send-btn {
    width: 40px;
    height: 40px;
  }

  .text-input-wrapper {
    padding: 7px 12px;
  }

  .text-input-wrapper textarea {
    font-size: 13px;
  }
}
</style>
