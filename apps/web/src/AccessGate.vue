<template>
  <App v-if="ready && accessState.authenticated" />
  <main v-else class="access-screen">
    <form class="access-card" @submit.prevent="signIn">
      <img :src="`${baseUrl}xiaonuan-avatar.svg`" alt="小暖" width="64" height="64" />
      <h1>小暖</h1>
      <p v-if="!ready">正在连接…</p>
      <template v-else-if="accessState.mode === 'key'">
        <p>输入管理员提供的访问密钥，进入你的陪伴空间。</p>
        <label for="access-key">访问密钥</label>
        <input id="access-key" v-model="key" type="password" autocomplete="off" spellcheck="false" required />
        <button :disabled="busy || !key.trim()">{{ busy ? '登录中…' : '进入' }}</button>
      </template>
      <p v-else>服务端目前仅允许本机访问，请在本机打开，或先配置访问密钥。</p>
      <p v-if="message || accessState.error" role="alert">{{ message || accessState.error }}</p>
      <button type="button" class="retry" :disabled="busy" @click="connect">重新连接</button>
    </form>
  </main>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue';
import App from './App.vue';
import { accessState, checkAccess, loginAccess } from './composables/accessSession';
const baseUrl = import.meta.env.BASE_URL;
const ready = ref(false), busy = ref(false), key = ref(''), message = ref('');
async function connect() {
  busy.value = true; message.value = '';
  try { await checkAccess(); ready.value = true; }
  catch (error) { message.value = error instanceof Error ? error.message : '连接失败'; ready.value = true; accessState.authenticated = false; }
  finally { busy.value = false; }
}
async function signIn() {
  if (busy.value) return;
  busy.value = true; message.value = '';
  try { await loginAccess(key.value.trim()); }
  catch (error) { message.value = error instanceof Error ? error.message : '登录失败'; }
  finally { key.value = ''; busy.value = false; }
}
onMounted(connect);
</script>
<style scoped>
.access-screen { min-height: 100dvh; display: grid; place-items: center; padding: 24px; background: #0d1220; color: #e2e8f0; box-sizing: border-box; }
.access-card { width: min(100%, 360px); padding: 28px; border: 1px solid #334155; border-radius: 20px; background: #151b2e; display: grid; gap: 14px; }
h1, p { margin: 0; }
p { font-size: 14px; line-height: 1.6; color: #b6c1d2; }
[role=alert] { color: #fda4af; }
input { min-width: 0; padding: 12px; border-radius: 10px; border: 1px solid #475569; background: #0f172a; color: white; font: inherit; }
button { padding: 12px; border: 0; border-radius: 10px; background: #c93960; color: white; cursor: pointer; font: inherit; }
button:disabled { opacity: .5; cursor: default; }
.retry { background: transparent; color: #cbd5e1; }
</style>
