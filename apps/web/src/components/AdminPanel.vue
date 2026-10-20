<template>
  <section class="admin-panel" aria-label="服务管理">
    <div class="panel-heading"><h4>{{ section === 'extensions' ? '扩展目录' : '运行状态' }}</h4>
      <button type="button" :disabled="loading || !!installing" @click="load">刷新</button></div>
    <p v-if="loading" role="status">正在加载…</p>
    <p v-if="notice" :role="failed ? 'alert' : 'status'">{{ notice }}</p>
    <template v-if="section === 'overview' && overview">
      <div class="status-cards">
        <article><span>服务</span><strong>{{ overview.ready ? '运行中' : '尚未就绪' }}</strong></article>
        <article><span>数据存储</span><strong>{{ overview.storage_mode === 'sqlite' ? '本地 SQLite' : 'PostgreSQL' }}</strong></article>
        <article><span>访问方式</span><strong>{{ overview.access_mode === 'key' ? '账号登录' : '仅本机' }}</strong></article>
      </div>
      <h5>启动检查</h5>
      <ul class="module-list"><li v-for="(status, name) in overview.modules" :key="name">
        <span>{{ moduleLabels[name] || name }}</span><strong :class="{ good: status === 'ready' }">{{ moduleStatus(status) }}</strong>
      </li></ul>
      <p class="hint">此处显示当前进程的启动状态。模型和语音连接可在对应配置页单独测试。</p>
      <h5>聊天平台</h5>
      <p v-if="!overview.platforms || overview.platforms.state === 'disabled'" class="hint">多平台尚未启用，需由宿主绑定账号和聊天目标。</p>
      <p v-else-if="overview.platforms.state === 'invalid'" role="alert">平台配置暂不可用，接收与回复已停止。</p>
      <ul v-else class="module-list"><li v-for="account in overview.platforms.accounts" :key="account.id">
        <span>{{ account.platform }} · {{ account.id }}</span>
        <strong>{{ platformStatus(account.receive_state) }}{{ account.reply ? ' · 可回复' : ' · 回复关闭' }}</strong>
      </li></ul>
    </template>
    <template v-if="section === 'extensions' && catalog">
      <p class="hint">随应用提供的本地扩展。安装不会授予执行权限，启用及用户范围由宿主管理。</p>
      <p v-if="!catalog.installation_enabled" class="hint">宿主尚未开放安装；你仍可浏览目录与已安装状态。</p>
      <article v-for="item in catalog.entries" :key="item.id" class="extension-card">
        <div class="panel-heading"><h5>{{ item.name }}</h5><span>v{{ item.version }}</span></div>
        <p>{{ item.description }}</p><p class="hint">{{ item.permissions }}</p>
        <span class="extension-state">{{ item.installed ? pluginStatus(item.runtime_status) : '未安装' }}</span>
        <button v-if="!item.installed" type="button" :disabled="!catalog.installation_enabled || !!installing"
          @click="pending = item">{{ installing === item.id ? '安装中…' : '查看并安装' }}</button>
      </article>
      <h5>已发现的扩展</h5>
      <p v-if="!plugins.length" class="hint">暂无已安装的扩展。</p>
      <ul class="module-list"><li v-for="item in plugins" :key="item.id">
        <span>{{ item.name || item.id }} <small v-if="item.version">v{{ item.version }}</small></span>
        <strong>{{ pluginStatus(item.status) }}{{ item.using_previous ? '（保留旧版）' : '' }}</strong>
      </li></ul>
    </template>
    <dialog v-if="pending" ref="reviewDialog" class="install-review" role="dialog" aria-label="安装扩展确认" @cancel="pending = null">
      <h5>安装 {{ pending.name }} v{{ pending.version }}</h5>
      <p>{{ pending.permissions }}</p><p>文件会放入宿主指定的扩展目录。已有同名目录不会覆盖，安装不更改宿主授权。</p>
      <button type="button" @click="pending = null">取消</button>
      <button type="button" @click="install(pending)">确认安装</button>
    </dialog>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue';
import { ACCESS_API_BASE, accessState, apiFetch, canManage } from '../composables/accessSession';
type CatalogEntry = { id: string; name: string; version: string; description: string; permissions: string; sha256: string; installed: boolean; runtime_status: string };
type Plugin = { id: string; name?: string; version?: string; status: string; using_previous?: boolean };
type Overview = { ready: boolean; storage_mode: string; access_mode: string; modules: Record<string, string>;
  platforms?: { state: string; accounts: { id: string; platform: string; receive_state: string; reply: boolean }[] } };
const props = defineProps<{ section: 'overview' | 'extensions' }>();
const overview = ref<Overview | null>(null);
const catalog = ref<{ installation_enabled: boolean; entries: CatalogEntry[] } | null>(null);
const plugins = ref<Plugin[]>([]), pending = ref<CatalogEntry | null>(null);
const loading = ref(false), installing = ref(''), notice = ref(''), failed = ref(false);
const reviewDialog = ref<HTMLDialogElement | null>(null);
function platformStatus(status: string): string {
  return ({ connected: '已连接', starting: '连接中', disabled: '接收关闭', waiting_callback: '等待平台回调', unavailable: '连接异常' } as Record<string, string>)[status] || '状态未知';
}
watch(pending, async value => { if (value) { await nextTick(); reviewDialog.value?.showModal?.(); } });
let generation = 0;
const moduleLabels: Record<string, string> = { database: '数据库', persona_engine: '人格与情绪', memory_system: '记忆',
  voice_layer: '语音', action_layer: '动作呈现', action_executor: '任务与工具', device_coordination: '设备网关',
  core_orchestrator: '对话编排', gateway_adapter: '平台入口' };
function moduleStatus(status: string) { return ({ ready: '就绪', failed: '启动失败', starting: '启动中' } as Record<string, string>)[status] || '未就绪'; }
function pluginStatus(status: string) { return ({ loaded: '已加载', disabled: '已安装，未启用', load_failed: '加载失败',
  invalid_config: '宿主配置无效', invalid_manifest: '扩展文件无效' } as Record<string, string>)[status] || '待检查'; }
async function request(path: string, options?: RequestInit) {
  const response = await apiFetch(`${ACCESS_API_BASE}${path}`, options);
  if (!response.ok) throw new Error(response.status === 403 ? '此操作需要管理员及宿主授权。' : '请求失败，请刷新后重试。');
  return response.json();
}
async function load() {
  const version = ++generation;
  overview.value = null; catalog.value = null; plugins.value = []; pending.value = null;
  notice.value = ''; failed.value = false; loading.value = true;
  if (!canManage.value) { loading.value = false; return; }
  try {
    if (props.section === 'overview') {
      const data = await request('/orchestrator/admin/overview');
      if (version === generation) overview.value = data;
    } else {
      const [directory, installed] = await Promise.all([request('/actions/plugins/catalog'), request('/actions/plugins')]);
      if (version === generation) { catalog.value = directory; plugins.value = installed.plugins; }
    }
  } catch (error) {
    if (version === generation) { failed.value = true; notice.value = error instanceof Error ? error.message : '加载失败。'; }
  } finally { if (version === generation) loading.value = false; }
}
async function install(item: CatalogEntry) {
  if (installing.value || !canManage.value) return;
  const version = generation;
  installing.value = item.id; pending.value = null; notice.value = ''; failed.value = false;
  try {
    await request(`/actions/plugins/catalog/${encodeURIComponent(item.id)}/install`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sha256: item.sha256 }),
    });
    if (version === generation) {
      const refresh = load(), refreshed = generation;
      await refresh;
      if (refreshed === generation && !failed.value) notice.value = '已安装；执行权限仍由宿主授权。';
    }
  } catch (error) {
    if (version === generation) { failed.value = true; notice.value = error instanceof Error ? error.message : '安装失败。'; }
  } finally { installing.value = ''; }
}
watch(() => [props.section, accessState.userId, accessState.role], load, { immediate: true });
onUnmounted(() => { generation++; });
</script>

<style scoped>
.admin-panel { position: relative; color: #dce3ef; font-size: 13px; }
.panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
h4 { margin: 0; font-size: 17px; } h5 { margin: 18px 0 10px; font-size: 14px; }
.hint, small { color: #a9b5c8; line-height: 1.7; }
.status-cards { display: grid; gap: 10px; margin-top: 20px; }
article { border: 1px solid #ffffff20; border-radius: 10px; padding: 14px; margin: 12px 0; }
.status-cards article { display: flex; justify-content: space-between; margin: 0; }
button { padding: 8px 12px; background: #fb71851a; border: 1px solid #fb718555; border-radius: 8px; color: #fecdd3; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
.module-list { list-style: none; margin: 0; padding: 0; }
li { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid #ffffff12; }
li strong { text-align: right; font-weight: normal; } .good { color: #86efac; }
.extension-state { display: inline-block; margin-right: 10px; color: #b9c5d9; }
.extension-card h5 { margin: 0; }
.install-review { color: inherit; width: min(360px, calc(100vw - 64px)); border: 1px solid #f7b1c0; padding: 16px; background: #242a3c; border-radius: 12px; }
.install-review::backdrop { background: #101321aa; }
.install-review button { margin: 8px 8px 0 0; }
</style>
