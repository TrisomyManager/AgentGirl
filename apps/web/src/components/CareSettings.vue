<template>
  <section aria-label="主动陪伴设置">
    <h4>主动陪伴</h4>
    <p v-if="loading" role="status">加载中…</p>
    <form v-if="preferences" class="care-settings" @submit.prevent="save">
      <fieldset :disabled="saving">
        <label><input v-model="preferences.enabled" type="checkbox" /> 允许小暖主动联系我</label>
        <label>时区 <select v-model="preferences.timezone" aria-label="主动陪伴时区">
          <option v-for="zone in timezones" :key="zone" :value="zone">{{ zone }}</option>
          <option v-if="!timezones.includes(preferences.timezone)" :value="preferences.timezone">{{ preferences.timezone }}</option>
        </select></label>
        <label>免打扰开始 <input v-model.number="preferences.dnd_start_hour" type="number" min="0" max="23" required /> 点</label>
        <label>免打扰结束 <input v-model.number="preferences.dnd_end_hour" type="number" min="0" max="23" required /> 点</label>
        <label>每天最多 <input v-model.number="preferences.max_per_day" type="number" min="0" max="20" required /> 条</label>
        <label>消息至少间隔 <input v-model.number="preferences.cooldown_minutes" type="number" min="1" max="10080" required /> 分钟</label>
        <label v-for="rule in rules" :key="rule.key"><input v-model="preferences[rule.key]" type="checkbox" /> {{ rule.title }}</label>
        <p>免打扰起止时间相同表示全天可联系；这些设置不影响你主动创建的提醒。</p>
        <button type="submit">{{ saving ? '保存中…' : '保存陪伴设置' }}</button>
      </fieldset>
    </form>
    <p v-if="notice" :role="failed ? 'alert' : 'status'">{{ notice }}</p>
    <button v-if="failed && !preferences" type="button" @click="load">重新加载</button>
  </section>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import { useApi, type CarePreferences } from '../composables/useApi';
const props = defineProps<{ userId: string }>();
const emit = defineEmits<{ (e: 'saved'): void }>();
const { getCarePreferences, saveCarePreferences } = useApi();
const preferences = ref<CarePreferences | null>(null);
const loading = ref(false), saving = ref(false), failed = ref(false), notice = ref('');
const timezones = ['Asia/Shanghai', 'Asia/Tokyo', 'Europe/London', 'America/New_York', 'America/Los_Angeles', 'UTC'];
const rules = [
  { key: 'morning_greeting', title: '早晨问候' }, { key: 'evening_greeting', title: '晚间问候' },
  { key: 'idle_checkin', title: '空闲关怀' }, { key: 'memory_followup', title: '记忆回访' },
] as const;
let generation = 0;
async function load() {
  const version = ++generation;
  loading.value = true; saving.value = false; preferences.value = null; notice.value = ''; failed.value = false;
  try {
    const data = await getCarePreferences(props.userId);
    if (version === generation) preferences.value = data;
  } catch {
    if (version === generation) { failed.value = true; notice.value = '加载陪伴设置失败，请重试。'; }
  } finally { if (version === generation) loading.value = false; }
}
async function save() {
  if (!preferences.value || saving.value) return;
  const version = generation, user = props.userId;
  saving.value = true; failed.value = false; notice.value = '';
  try {
    const data = await saveCarePreferences(user, { ...preferences.value });
    if (version === generation) { preferences.value = data; notice.value = '已保存'; emit('saved'); }
  } catch {
    if (version === generation) { failed.value = true; notice.value = '保存陪伴设置失败，请重试。'; }
  } finally { if (version === generation) saving.value = false; }
}
watch(() => props.userId, load, { immediate: true });
onUnmounted(() => { generation++; });
</script>

<style scoped>
section { color: #dce3ef; font-size: 13px; }
h4 { margin-top: 0; font-size: 16px; }
fieldset { display: grid; gap: 14px; border: 0; padding: 0; margin: 0; min-width: 0; }
label { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
input, select { accent-color: #f6a5bb; color: inherit; background: #202638; border: 1px solid #697389; border-radius: 6px; padding: 5px; max-width: 100%; }
input[type=number] { width: 75px; }
p { line-height: 1.7; color: #afbacc; }
button { padding: 9px 12px; border: 1px solid #fb718555; border-radius: 8px; background: #fb71851a; color: #fecdd3; cursor: pointer; }
fieldset:disabled { opacity: .6; }
</style>
