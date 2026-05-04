<template>
  <div class="app-root">
    <!-- Top bar -->
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

    <!-- Offline banner -->
    <div v-if="serverAvailable === false" class="banner banner-offline">
      <span>⚠️ 离线模式 - 服务器未连接，部分功能不可用</span>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="banner banner-error">
      <span>{{ error }}</span>
      <button class="banner-close" @click="clearError">✕</button>
    </div>

    <!-- Main layout -->
    <div class="main-layout">
      <!-- Left sidebar: avatar -->
      <aside class="sidebar">
        <AvatarDisplay
          :emotion-label="emotionLabel"
          :emotion="currentEmotion"
          :action-label="actionLabel"
          :is-typing="isTyping"
        />
      </aside>

      <!-- Right chat area -->
      <section class="chat-area">
        <div class="messages-container" ref="messagesContainerRef">
          <div class="messages-inner">
            <ChatMessage
              v-for="msg in messages"
              :key="msg.id"
              :message="msg"
            />

            <!-- Typing indicator -->
            <div v-if="isTyping" class="typing-row">
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

        <LlmStatusBar />
        <ChatInput
          :is-loading="isLoading"
          :voice="voice"
          @send="sendMessage"
        />
      </section>
    </div>

    <!-- Settings drawer -->
    <SettingsDrawer
      :visible="settingsVisible"
      :user-name="userName"
      :session-id="sessionId"
      :server-available="serverAvailable"
      @close="settingsVisible = false"
      @update:user-name="updateUserName"
      @clear="clearHistory"
    />

    <!-- Project status panel -->
    <ProjectStatusPanel
      :visible="statusVisible"
      @close="statusVisible = false"
    />

    <!-- Voice call panel -->
    <VoiceCallPanel
      :visible="callVisible"
      @close="callVisible = false"
    />

    <!-- Memory viewer -->
    <MemoryViewer
      :visible="memoryVisible"
      :user-id="userId"
      @close="memoryVisible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue';
import TopBar from './components/TopBar.vue';
import ChatMessage from './components/ChatMessage.vue';
import ChatInput from './components/ChatInput.vue';
import AvatarDisplay from './components/AvatarDisplay.vue';
import SettingsDrawer from './components/SettingsDrawer.vue';
import ProjectStatusPanel from './components/ProjectStatusPanel.vue';
import LlmStatusBar from './components/LlmStatusBar.vue';
import VoiceCallPanel from './components/VoiceCallPanel.vue';
import MemoryViewer from './components/MemoryViewer.vue';
import { useChat } from './composables/useChat';

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
} = useChat();

const settingsVisible = ref(false);
const statusVisible = ref(false);
const callVisible = ref(false);
const memoryVisible = ref(false);
const messagesContainerRef = ref<HTMLElement | null>(null);

function scrollToBottom() {
  nextTick(() => {
    const el = messagesContainerRef.value;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  });
}

// Auto-scroll when messages change or typing state changes
watch(messages, scrollToBottom, { deep: true });
watch(isTyping, scrollToBottom);

onMounted(() => {
  checkServer();
  scrollToBottom();
});
</script>

<style scoped>
.app-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background: #0d0d1a;
  color: #e2e8f0;
  font-family: 'Inter', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
    sans-serif;
  overflow: hidden;
}

/* Banners */
.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 20px;
  font-size: 13px;
  flex-shrink: 0;
  gap: 12px;
}

.banner-offline {
  background: rgba(245, 158, 11, 0.12);
  border-bottom: 1px solid rgba(245, 158, 11, 0.25);
  color: #fbbf24;
}

.banner-error {
  background: rgba(239, 68, 68, 0.12);
  border-bottom: 1px solid rgba(239, 68, 68, 0.25);
  color: #f87171;
}

.banner-close {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 6px;
  border-radius: 4px;
  opacity: 0.7;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}

.banner-close:hover {
  opacity: 1;
}

/* Main layout */
.main-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Left sidebar */
.sidebar {
  width: 320px;
  flex-shrink: 0;
  background: rgba(13, 13, 30, 0.6);
  border-right: 1px solid rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

/* Right chat area */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Messages scroll container */
.messages-container {
  flex: 1;
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
  background: rgba(255, 255, 255, 0.08);
  border-radius: 4px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.15);
}

.messages-inner {
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
}

/* Typing indicator row */
.typing-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin-bottom: 16px;
  animation: fadeInUp 0.3s ease;
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

.typing-bubble {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 16px;
  background: #1a1a2e;
  border-radius: 16px;
  border-bottom-left-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.typing-bubble span {
  width: 8px;
  height: 8px;
  background: #64748b;
  border-radius: 50%;
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

/* Responsive: collapse sidebar on narrow screens */
@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
}
</style>
