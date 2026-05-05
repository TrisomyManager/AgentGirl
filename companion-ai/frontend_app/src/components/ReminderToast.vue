<template>
  <transition name="toast">
    <div v-if="reminder" class="reminder-toast" role="status" aria-live="polite">
      <div class="bell">
        <span aria-hidden="true">⏰</span>
      </div>
      <div class="copy">
        <p class="title">小暖的提醒</p>
        <p class="body">{{ reminder.text }}</p>
        <p class="meta">{{ formattedTime }}</p>
      </div>
      <button class="dismiss" type="button" @click="emit('dismiss')" aria-label="关闭提醒">
        ×
      </button>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ReminderFiredPayload } from '../composables/useProactivePush';

const props = defineProps<{
  reminder: ReminderFiredPayload | null;
}>();

const emit = defineEmits<{
  (e: 'dismiss'): void;
}>();

const formattedTime = computed(() => {
  if (!props.reminder?.fire_at) return '';
  const date = new Date(props.reminder.fire_at);
  if (Number.isNaN(date.getTime())) return props.reminder.fire_at;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
});
</script>

<style scoped>
.reminder-toast {
  position: fixed;
  z-index: 9000;
  top: 22px;
  right: 22px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: min(360px, calc(100% - 44px));
  padding: 14px 14px 14px 18px;
  border-radius: 18px;
  border: 1px solid rgba(233, 69, 96, 0.45);
  background:
    radial-gradient(circle at top right, rgba(233, 69, 96, 0.18), transparent 55%),
    rgba(15, 23, 42, 0.92);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(10px);
  color: #f8fafc;
}

.bell {
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  background: rgba(233, 69, 96, 0.18);
  border: 1px solid rgba(233, 69, 96, 0.32);
  animation: ringPulse 1.6s ease-in-out infinite;
}

@keyframes ringPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}

.copy {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #fda4af;
  letter-spacing: 0.04em;
}

.body {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: #f8fafc;
  word-break: break-word;
}

.meta {
  margin: 0;
  font-size: 11px;
  color: #94a3b8;
}

.dismiss {
  flex: 0 0 auto;
  background: transparent;
  border: none;
  color: #cbd5e1;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.dismiss:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f8fafc;
}

.toast-enter-active,
.toast-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-12px) scale(0.96);
}

@media (max-width: 480px) {
  .reminder-toast {
    top: 12px;
    right: 12px;
    left: 12px;
    width: auto;
  }
}
</style>
