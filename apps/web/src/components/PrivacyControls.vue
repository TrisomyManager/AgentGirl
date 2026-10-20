<template>
  <section class="privacy-controls" aria-label="数据与隐私">
    <h4>数据与隐私</h4>
    <p>导出或删除此账号在服务端保存的对话、记忆、画像、关系、提醒、任务和语音文件。</p>
    <p>宿主备份、其他浏览器缓存、AI 服务商记录及已发送到第三方的操作结果需要分别处理。</p>
    <p>清理后仅保留不含对话内容的清理状态，以及管理员配置的账号身份。</p>
    <button type="button" :disabled="busy" @click="download">{{ exporting ? '导出中…' : '下载我的数据' }}</button>
    <form v-if="status !== 'completed'" @submit.prevent="erase">
      <label :for="inputId">输入“删除我的全部数据”确认</label>
      <input :id="inputId" v-model="confirmation" :disabled="busy" autocomplete="off" />
      <button class="erase" :disabled="busy || confirmation !== phrase">
        {{ deleting ? '正在停止任务并清理…' : status === 'pending' ? '重试剩余清理' : '删除我的全部数据' }}
      </button>
    </form>
    <p v-if="status === 'pending'" role="status">部分清理尚未完成，账号数据写入已暂停。请重试，完成前不会恢复聊天。</p>
    <p v-if="status === 'completed'" role="status">服务端数据已清理，本机记录已移除。</p>
    <button v-if="status === 'completed' || error" type="button" @click="restart">{{ status === 'completed' ? '重新开始' : '重新连接' }}</button>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ACCESS_API_BASE, apiFetch } from '../composables/accessSession';
const props = defineProps<{ userId: string }>();
const emit = defineEmits<{ (event: 'clearing', value: boolean): void; (event: 'cleared'): void }>();
const phrase = '删除我的全部数据';
const confirmation = ref(''), status = ref('none'), error = ref('');
const exporting = ref(false), deleting = ref(false);
const busy = computed(() => exporting.value || deleting.value);
const inputId = `privacy-confirm-${props.userId}`;
const url = (action: string) => `${ACCESS_API_BASE}/privacy/user/${encodeURIComponent(props.userId)}/${action}`;
async function detail(response: Response) {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === 'string' ? body.detail : '操作失败，请重试。';
}
onMounted(async () => {
  try {
    const response = await apiFetch(url('status'));
    if (response.ok && (await response.json()).status === 'pending') { status.value = 'pending'; emit('clearing', true); }
  } catch { /* Operations report connection errors when requested. */ }
});
async function download() {
  exporting.value = true; error.value = '';
  try {
    const response = await apiFetch(url('export'));
    if (!response.ok) throw new Error(await detail(response));
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement('a'); link.href = objectUrl; link.download = 'companion-user-data.json';
    link.click(); setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '导出失败'; }
  finally { exporting.value = false; }
}
async function erase() {
  if (busy.value || confirmation.value !== phrase) return;
  deleting.value = true; error.value = ''; emit('clearing', true);
  try {
    const response = await apiFetch(url('erase'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmation: phrase }),
    });
    if (!response.ok) throw new Error(await detail(response));
    status.value = (await response.json()).status;
    confirmation.value = ''; emit('cleared');
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '清理失败';
    // A lost response can follow a committed deletion. Keep chat paused until reload/retry.
  } finally { deleting.value = false; }
}
function restart() { window.location.reload(); }
</script>
<style scoped>
.privacy-controls { display: grid; gap: 12px; padding: 18px 0; border-top: 1px solid #475569; color: #e2e8f0; }
h4, p { margin: 0; } p { font-size: 13px; line-height: 1.6; color: #cbd5e1; }
form { display: grid; gap: 10px; } label { font-size: 13px; }
input, button { padding: 10px; border: 1px solid #475569; border-radius: 8px; background: #1e293b; color: #e2e8f0; font: inherit; }
button { cursor: pointer; } button:disabled { opacity: .5; cursor: default; } .erase { color: #fda4af; border-color: #9f3450; }
[role=alert] { color: #fda4af; }
</style>
