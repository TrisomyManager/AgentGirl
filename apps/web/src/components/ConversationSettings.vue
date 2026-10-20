<template>
  <section class="conversation-settings" aria-label="聊天节奏设置">
    <h4>聊天节奏</h4>
    <p v-if="loading" role="status">加载中…</p>
    <template v-else-if="preferences">
      <form @submit.prevent="save">
        <fieldset :disabled="saving">
          <label class="mode-toggle">
            <input v-model="preferences.natural_reply_enabled" type="checkbox" />
            自然发言，简短回应后偶尔安静陪伴
          </label>
          <p class="help">只影响“嗯、好的”等独立的简短回应。问题、任务和等待确认的对话仍会回复，也不会连续两次保持安静。</p>
          <label class="probability">
            简短回应后继续聊天的概率 <strong>{{ Math.round(preferences.acknowledgement_reply_probability * 100) }}%</strong>
            <input v-model.number="preferences.acknowledgement_reply_probability" type="range" min="0" max="1" step="0.05"
              :disabled="!preferences.natural_reply_enabled" aria-label="简短回应后继续聊天的概率" />
          </label>
          <p class="help">仅在文字聊天且关闭自动语音时生效；0% 表示安静陪伴，100% 表示每次回应。</p>
          <button type="submit">{{ saving ? '保存中…' : '保存聊天节奏' }}</button>
        </fieldset>
      </form>
    </template>
    <p v-if="notice" :role="failed ? 'alert' : 'status'" :class="{ failed }">{{ notice }}</p>
    <button v-if="failed && !preferences" type="button" @click="load">重试</button>
  </section>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import { useApi, type ConversationPreferences } from '../composables/useApi';

const props = defineProps<{ userId: string }>();
const { getConversationPreferences, saveConversationPreferences } = useApi();
const preferences = ref<ConversationPreferences | null>(null);
const loading = ref(false);
const saving = ref(false);
const notice = ref('');
const failed = ref(false);
let requestVersion = 0;

async function load() {
  const version = ++requestVersion;
  loading.value = true;
  preferences.value = null;
  notice.value = '';
  failed.value = false;
  try {
    const data = await getConversationPreferences(props.userId);
    if (version === requestVersion) preferences.value = data;
  } catch (error) {
    if (version === requestVersion) {
      failed.value = true;
      notice.value = error instanceof Error ? error.message : '加载失败';
    }
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}

async function save() {
  if (!preferences.value || saving.value) return;
  const version = ++requestVersion;
  const user = props.userId;
  saving.value = true;
  notice.value = '';
  failed.value = false;
  try {
    const data = await saveConversationPreferences(user, { ...preferences.value });
    if (version === requestVersion) {
      preferences.value = data;
      notice.value = '已保存';
    }
  } catch (error) {
    if (version === requestVersion) {
      failed.value = true;
      notice.value = error instanceof Error ? error.message : '保存失败';
    }
  } finally {
    if (version === requestVersion) saving.value = false;
  }
}

watch(() => props.userId, () => { saving.value = false; void load(); }, { immediate: true });
onUnmounted(() => { requestVersion += 1; });
</script>

<style scoped>
.conversation-settings { padding: 18px 0; border-top: 1px solid #ffffff15; color: #e2e8f0; }
h4 { margin: 0 0 14px; font-size: 15px; }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
label { font-size: 13px; line-height: 1.6; }
.mode-toggle { display: flex; align-items: flex-start; gap: 8px; }
.mode-toggle input { margin: 4px 0 0; accent-color: #fb7185; }
.help { color: #a3afc4; font-size: 12px; line-height: 1.7; margin: 10px 0 16px; }
.probability { display: block; }
.probability strong { color: #fda4af; margin-left: 4px; }
input[type='range'] { display: block; width: 100%; margin: 12px 0; accent-color: #fb7185; }
button { border: 1px solid #fb718555; border-radius: 8px; background: #fb71851a; color: #fecdd3; padding: 8px 12px; cursor: pointer; }
fieldset:disabled { opacity: 0.65; }
p[role] { font-size: 12px; color: #86efac; }
p.failed { color: #fca5a5; }
</style>
