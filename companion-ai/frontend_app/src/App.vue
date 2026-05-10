<template>
  <div class="app-root">
    <div class="app-backdrop"></div>

    <main class="app-shell">
      <TopBar
        :emotion-label="emotionLabel"
        :emotion="currentEmotion"
        :server-available="serverAvailable"
        :voice="voice"
        @open-settings="settingsVisible = true"
        @open-status="statusVisible = true"
        @open-call="callVisible = true"
        @open-memory="memoryVisible = true"
      />

      <div v-if="serverAvailable === false" class="banner banner-offline">
        <span>⚠️ 离线模式，服务器暂未连接，部分能力会降级。</span>
      </div>

      <div v-if="error" class="banner banner-error">
        <span>{{ error }}</span>
        <button class="banner-close" @click="clearError">✕</button>
      </div>

      <div class="main-layout">
        <aside class="sidebar">
          <AvatarDisplay
            :emotion-label="emotionLabel"
            :emotion="currentEmotion"
            :action-label="actionLabel"
            :is-typing="isTyping"
          />
        </aside>

        <section class="chat-area">
          <div class="messages-container" ref="messagesContainerRef">
            <div class="messages-inner">
              <ChatMessage
                v-for="msg in messages"
                :key="msg.id"
                :message="msg"
                :voice="voice"
                :tool-execution="msg.isTyping ? currentToolExecution : null"
                @assistant-voice-playback="handleAssistantVoicePlayback"
              />

              <div v-if="isTyping && !hasStreamingContent" class="typing-row">
                <div class="msg-avatar">
                  <img
                    src="https://placehold.co/36x36/e94560/FFF?text=暖"
                    alt="小暖"
                  />
                </div>
                <div class="typing-bubble">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="currentToolExecution?.status === 'pending'" class="tool-status-bar" role="status" aria-live="polite">
            <span class="tool-status-icon" aria-hidden="true">🔄</span>
            <span class="tool-status-text">{{ toolStatus.currentToolLabel.value }}中…</span>
          </div>
          <LlmStatusBar />
          <ChatInput
            :is-loading="isLoading"
            :voice="voice"
            @send="sendMessage"
          />
        </section>
      </div>
    </main>

    <SettingsDrawer
      :visible="settingsVisible"
      :user-name="userName"
      :session-id="sessionId"
      :server-available="serverAvailable"
      @close="settingsVisible = false"
      @update:user-name="updateUserName"
      @clear="clearHistory"
    />

    <ProjectStatusPanel
      :visible="statusVisible"
      @close="statusVisible = false"
    />

    <VoiceCallPanel
      :visible="callVisible"
      @close="callVisible = false"
      @open-settings="callVisible = false; settingsVisible = true"
    />

    <MemoryViewer
      :visible="memoryVisible"
      :user-id="userId"
      @close="memoryVisible = false"
    />

    <ReminderToast
      :reminder="lastReminder"
      @dismiss="dismissLastReminder"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import TopBar from './components/TopBar.vue';
import ChatMessage from './components/ChatMessage.vue';
import ChatInput from './components/ChatInput.vue';
import AvatarDisplay from './components/AvatarDisplay.vue';
import SettingsDrawer from './components/SettingsDrawer.vue';
import ProjectStatusPanel from './components/ProjectStatusPanel.vue';
import LlmStatusBar from './components/LlmStatusBar.vue';
import VoiceCallPanel from './components/VoiceCallPanel.vue';
import MemoryViewer from './components/MemoryViewer.vue';
import ReminderToast from './components/ReminderToast.vue';
import { useChat } from './composables/useChat';
import { useProactivePush } from './composables/useProactivePush';
import type { ToolExecutionState } from './composables/useToolStatus';

const {
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
  clearError,
  checkServer,
  handleAssistantVoicePlayback,
  toolStatus,
} = useChat();

// Subscribe to /actions/push (SSE) so reminder_fired events surface as a
// floating toast in the corner. dismissLastReminder is wired to the toast's
// close button.
const { lastReminder, dismissLastReminder } = useProactivePush();

// Current tool execution state (for ChatMessage and global banner)
const currentToolExecution = computed<ToolExecutionState | null>(
  () => toolStatus.currentTool.value,
);

// Suppress the global typing dots whenever the latest assistant message is
// still in a typing state — that bubble (ChatMessage) already renders its
// own typing-indicator (when content is empty) or a streaming cursor (once
// chunks arrive). Showing the global dots on top would be a duplicate.
const hasStreamingContent = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i];
    if (m.role !== 'assistant') break;
    if (m.isTyping) return true;
    if (!m.isTyping) break;
  }
  return false;
});

const settingsVisible = ref(false);
const statusVisible = ref(false);
const callVisible = ref(false);
const memoryVisible = ref(false);
const messagesContainerRef = ref<HTMLElement | null>(null);

function scrollToBottom() {
  nextTick(() => {
    const element = messagesContainerRef.value;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  });
}

watch(messages, scrollToBottom, { deep: true });
watch(isTyping, scrollToBottom);

onMounted(() => {
  checkServer();
  scrollToBottom();
});
</script>

<style scoped>
:global(html, body, #app) {
  width: 100%;
  max-width: 100%;
  height: 100%;
  min-height: 100dvh;
  margin: 0;
  box-sizing: border-box;
}

:global(body) {
  overflow: hidden;
  overflow-x: clip;
  background: #060913;
}

:global(#app) {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 100dvh;
  min-width: 0;
}

.app-root {
  --frame-gap: clamp(10px, 1.8vw, 24px);
  --shell-max: 1400px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 100dvh;
  min-height: 100dvh;
  padding: var(--frame-gap);
  overflow: hidden;
  color: #e2e8f0;
  font-family: 'Avenir Next', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
    sans-serif;
  background:
    radial-gradient(circle at top left, rgba(233, 69, 96, 0.18), transparent 26%),
    radial-gradient(circle at top right, rgba(96, 165, 250, 0.18), transparent 24%),
    linear-gradient(180deg, #060913 0%, #0b1020 46%, #080c17 100%);
}

.app-backdrop {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(130deg, rgba(255, 255, 255, 0.03), transparent 32%),
    radial-gradient(circle at 20% 18%, rgba(255, 255, 255, 0.05), transparent 16%);
}

.app-shell {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  /* 用 100% 避免 100vw 含滚动条导致整体偏右 */
  width: 100%;
  max-width: min(var(--shell-max), 100%);
  margin-inline: auto;
  flex: 0 1 auto;
  align-self: center;
  height: calc(100dvh - (var(--frame-gap) * 2));
  max-height: calc(100dvh - (var(--frame-gap) * 2));
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 32px;
  background:
    linear-gradient(180deg, rgba(15, 21, 37, 0.96), rgba(8, 12, 24, 0.98));
  box-shadow:
    0 28px 80px rgba(0, 0, 0, 0.46),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(16px);
}

.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 24px;
  font-size: 13px;
  flex-shrink: 0;
}

.banner-offline {
  color: #fcd34d;
  background: rgba(120, 53, 15, 0.22);
  border-bottom: 1px solid rgba(245, 158, 11, 0.18);
}

.banner-error {
  color: #fca5a5;
  background: rgba(127, 29, 29, 0.24);
  border-bottom: 1px solid rgba(248, 113, 113, 0.16);
}

.banner-close {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  opacity: 0.78;
  font-size: 13px;
  padding: 2px 6px;
}

.banner-close:hover {
  opacity: 1;
}

.main-layout {
  display: flex;
  flex: 1;
  gap: 14px;
  min-height: 0;
  min-width: 0;
  height: 100%;
  padding: 14px;
  overflow: hidden;
  align-items: stretch;
}

.sidebar {
  width: clamp(240px, 25vw, 340px);
  min-width: 240px;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 26px;
  background:
    linear-gradient(180deg, rgba(20, 26, 42, 0.92), rgba(11, 16, 29, 0.94));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.chat-area {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 26px;
  background:
    linear-gradient(180deg, rgba(12, 18, 31, 0.9), rgba(8, 12, 22, 0.97));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.messages-container {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.messages-container::-webkit-scrollbar {
  width: 4px;
}

.messages-container::-webkit-scrollbar-track {
  background: transparent;
}

.messages-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 999px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.16);
}

.messages-inner {
  display: flex;
  flex-direction: column;
  padding: 28px 22px 18px;
}

.typing-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin-bottom: 16px;
  animation: fadeInUp 0.3s ease;
}

.msg-avatar {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}

.msg-avatar img {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
}

.typing-bubble {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 16px 16px 16px 4px;
  background: rgba(27, 34, 54, 0.92);
}

.typing-bubble span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #64748b;
  animation: typingBounce 1.4s ease-in-out infinite;
}

.typing-bubble span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-bubble span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typingBounce {
  0%, 60%, 100% {
    transform: translateY(0);
  }

  30% {
    transform: translateY(-6px);
  }
}

.tool-status-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 12px;
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.6);
  border-top: 1px solid rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(8px);
  animation: fadeInUp 0.25s ease;
  transition: all 0.25s ease;
}

.tool-status-icon {
  font-size: 13px;
  animation: toolSpin 1.5s linear infinite;
}

.tool-status-text {
  font-weight: 500;
  letter-spacing: 0.02em;
}

@keyframes toolSpin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
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

@media (max-width: 960px) {
  .app-root {
    --frame-gap: 10px;
  }

  .app-shell {
    border-radius: 24px;
  }

  .main-layout {
    padding: 10px;
    gap: 10px;
  }

  .sidebar {
    display: none;
  }

  .chat-area {
    border-radius: 22px;
  }
}

@media (max-width: 640px) {
  .app-root {
    --frame-gap: 0px;
  }

  .app-shell {
    width: 100%;
    height: 100dvh;
    border: none;
    border-radius: 0;
  }

  .banner {
    padding: 10px 14px;
    font-size: 12px;
  }

  .main-layout {
    padding: 8px;
  }

  .chat-area {
    border-radius: 20px        