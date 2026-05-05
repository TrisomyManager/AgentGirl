<template>
  <div class="message-wrapper" :class="message.role">
    <div v-if="message.role === 'assistant'" class="msg-avatar">
      <img
        src="https://placehold.co/36x36/e94560/FFF?text=暖"
        alt="小暖"
      />
    </div>

    <div class="message-content">
      <div class="message-bubble" :class="message.role">
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
import { computed } from 'vue';
import type { ChatMessage } from '../composables/useChat';

const props = defineProps<{
  message: ChatMessage;
}>();

const formattedTime = computed(() => {
  const date = new Date(props.message.timestamp);
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
});

function renderMarkdown(text: string): string {
  // Simple markdown: bold, italic, code, line breaks
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Bold **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic *text*
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Code `text`
  html = html.replace(/`(.+?)`/g, '<code>$1</code>');
  // Line breaks
  html = html.replace(/\n/g, '<br>');

  return html;
}

const renderedContent = computed(() => {
  if (props.message.isTyping && !props.message.content) return '';
  return renderMarkdown(props.message.content || '');
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
  50% { opacity: 0; }
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
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}
</style>
