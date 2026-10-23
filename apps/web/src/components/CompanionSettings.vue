<template>
  <section class="companion-settings">
    <h4>陪伴与功能</h4>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <fieldset :disabled="saving || !loaded">
      <legend>主动陪伴</legend>
      <label><input v-model="policy.enabled" type="checkbox" />接收主动关怀</label>
      <label><input v-model="policy.desktop_enabled" type="checkbox" :disabled="!bridge" />根据桌面情境关心我</label>
      <p class="hint">桌面情境仅传应用进程名、闲置时长和忙碌状态；不读取窗口标题、不截图。需在下方启用对应功能并重启服务。</p>
      <label>允许的应用（每行一个进程名）<textarea v-model="apps" rows="3" placeholder="Code.exe&#10;chrome.exe" /></label>
      <label>在同一应用停留（秒）<input v-model.number="policy.dwell_seconds" type="number" min="15" max="3600" /></label>
      <label>至少闲置（秒，0 表示不要求）<input v-model.number="policy.min_idle_seconds" type="number" min="0" max="3600" /></label>
      <button @click="savePolicy">保存陪伴偏好</button>
    </fieldset>
    <fieldset :disabled="saving || !loaded">
      <legend>全局可选功能</legend>
      <label v-for="feature in features" :key="feature.id">
        <input v-model="enabled" type="checkbox" :value="feature.id" />{{ feature.name }}
        <small>{{ feature.active ? '本次已启用' : '本次未启用' }}</small>
      </label>
      <p class="hint">作用于当前服务的所有用户，保存后需重启服务。核心对话、人格、记忆和设备保持启用；桌面情境依赖主动关怀。</p>
      <button @click="saveFeatures">保存功能选择</button>
    </fieldset>
    <fieldset v-if="bridge" :disabled="saving">
      <legend>桌宠</legend>
      <label><input :checked="petEnabled" type="checkbox" @change="togglePet" />显示桌宠</label>
      <label><input :checked="clickThrough" type="checkbox" @change="toggleThrough" />鼠标穿透</label>
      <button @click="choosePack">导入 dsh-pet 角色目录</button>
      <p class="hint">{{ packName || '未导入角色；桌宠使用默认占位角色' }}。支持源 WebM/GIF 包。素材留在本机，不上传；请使用有权使用的角色。</p>
      <p class="hint">开启穿透后，可从系统托盘“显示桌宠并恢复鼠标交互”找回。</p>
    </fieldset>
    <p v-else class="hint">桌宠与桌面情境采集在 Electron 客户端提供；网页可配置其余功能。</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { companionRequest, desktopBridge } from '../composables/desktopBridge';

const props = defineProps<{ userId: string }>();
const bridge = desktopBridge();
const loaded = ref(false), saving = ref(false), error = ref(''), notice = ref('');
const apps = ref('');
const policy = reactive({ enabled: true, desktop_enabled: false, allowed_apps: [] as string[], dwell_seconds: 45, min_idle_seconds: 0 });
const features = ref<Array<{ id: string; name: string; active: boolean }>>([]);
const enabled = ref<string[]>([]);
const petEnabled = ref(false), clickThrough = ref(false), packName = ref('');
const userQuery = () => `?user_id=${encodeURIComponent(props.userId)}`;
async function run(action: () => Promise<void>) {
  error.value = ''; notice.value = ''; saving.value = true;
  try { await action(); } catch (err) { error.value = err instanceof Error ? err.message : String(err); }
  finally { saving.value = false; }
}
onMounted(() => void run(async () => {
  // Local pet controls remain usable when the backend is offline.
  if (bridge) { const state = await bridge.petStatus(); petEnabled.value = state.enabled;
    clickThrough.value = state.clickThrough; packName.value = state.pack?.name ?? ''; }
  const [prefs, modules] = await Promise.all([companionRequest('/actions/proactive/preferences' + userQuery()),
    companionRequest('/settings/features')]);
  Object.assign(policy, prefs.policy); apps.value = policy.allowed_apps.join('\n');
  features.value = modules.features; enabled.value = modules.pending_enabled; loaded.value = true;
}));
async function savePolicy() { await run(async () => {
  await companionRequest('/actions/proactive/preferences' + userQuery(), 'PUT', {
    ...policy, allowed_apps: apps.value.split('\n').map(value => value.trim()).filter(Boolean),
  });
  window.dispatchEvent(new Event('companion-preferences-changed'));
  notice.value = '陪伴偏好已保存';
}); }
async function saveFeatures() { await run(async () => {
  const result = await companionRequest('/settings/features', 'PUT', { enabled: enabled.value });
  notice.value = result.restart_required ? '功能选择已保存，请重启后端服务后生效' : '功能选择已保存';
}); }
async function togglePet(event: Event) { await run(async () => {
  const next = (event.target as HTMLInputElement).checked;
  await bridge?.petSetEnabled(next); petEnabled.value = next;
}); }
async function toggleThrough(event: Event) { await run(async () => {
  const next = (event.target as HTMLInputElement).checked;
  await bridge?.petSetClickThrough(next); clickThrough.value = next;
}); }
async function choosePack() { await run(async () => { const pack = await bridge?.petChoosePack(); if (pack) packName.value = pack.name; }); }
</script>

<style scoped>
.companion-settings { margin: 20px 0; color: #d9e2f1; font-size: 13px; }
h4 { margin: 0 0 12px; font-size: 15px; }
fieldset { border: 1px solid #ffffff1a; border-radius: 12px; margin: 12px 0; padding: 12px; }
legend { color: #fda4af; padding: 0 6px; }
label { display: block; margin: 9px 0; }
input[type=checkbox] { margin-right: 8px; accent-color: #e94560; }
textarea, input[type=number] { display: block; box-sizing: border-box; width: 100%; margin-top: 6px; padding: 8px;
  border: 1px solid #ffffff20; border-radius: 8px; color: #e2e8f0; background: #101827; }
button { border: 1px solid #fb718544; padding: 8px 12px; color: #fecdd3; background: #e9456020; border-radius: 8px; cursor: pointer; }
.hint, small { color: #94a3b8; font-size: 12px; line-height: 1.6; }
small { margin-left: 8px; }.error { color: #fda4af; }
</style>
