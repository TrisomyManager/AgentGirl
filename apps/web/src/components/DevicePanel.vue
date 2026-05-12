<template>
  <div class="device-panel-section">
    <div v-if="loading" class="status-box"><span class="spinner"></span><span>加载中…</span></div>
    <div v-else-if="error" class="status-box error"><span>{{ error }}</span></div>
    <div v-else-if="!devices.length" class="empty-state">
      <p>还没有绑定任何设备。</p>
      <p class="empty-hint">安装小暖 PC 版并登录后，设备会自动出现在这里。</p>
    </div>
    <div v-else>
      <!-- Device list -->
      <div class="task-section">
        <div class="task-section-title">我的设备 ({{ devices.length }})</div>
        <div v-for="d in devices" :key="d.device_id" class="device-card">
          <div class="device-head">
            <span :class="['online-dot', d.is_online ? 'on' : 'off']"></span>
            <span class="device-name">{{ d.device_name || d.device_id }}</span>
            <span v-if="d.is_online" class="tag on">在线</span>
            <span v-else class="tag off">离线</span>
          </div>
          <div class="device-meta">
            <span>{{ d.platform }}</span>
            <span class="device-caps">{{ (d.capabilities || []).join(' / ') || '无' }}</span>
          </div>
          <div v-if="d.last_heartbeat" class="device-heartbeat">上次心跳：{{ formatHb(d.last_heartbeat) }}</div>
          <div class="device-actions" v-if="d.is_online">
            <button class="action-btn" @click="ping(d)" :disabled="acting">Ping</button>
            <button class="action-btn" @click="sendTestNotify(d)" :disabled="acting">测试通知</button>
          </div>
        </div>
      </div>

      <!-- Recent commands -->
      <div v-if="commands.length" class="task-section">
        <div class="task-section-title">最近指令</div>
        <div v-for="c in commands.slice(0, 10)" :key="c.command_id" class="cmd-row">
          <span class="cmd-icon">{{ cmdIcon(c.status) }}</span>
          <span class="cmd-cmd">{{ c.command }}</span>
          <span class="cmd-risk" v-if="c.risk_level">{{ c.risk_level }}</span>
          <span class="cmd-device">→ {{ c.device_id }}</span>
          <span class="cmd-updated" v-if="c.updated_at">{{ shortTime(c.updated_at) }}</span>
          <span :class="['cmd-status', `s-${c.status}`]">{{ statusLabel(c.status) }}</span>
        </div>
      </div>

      <div v-if="audit.length" class="task-section">
        <div class="task-section-title">最近审计</div>
        <div v-for="a in audit.slice(0, 8)" :key="a.audit_id" class="audit-row">
          <span class="audit-action">{{ a.action }}</span>
          <span class="audit-cmd">{{ a.command || '—' }}</span>
          <span class="audit-actor">{{ a.actor }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{ userId: string }>();

interface DeviceItem {
  device_id: string;
  user_id: string;
  device_name: string;
  device_type: string;
  platform: string;
  capabilities: string[];
  is_online: boolean;
  last_heartbeat: string;
}

interface CommandItem {
  command_id: string;
  device_id: string;
  command: string;
  status: string;
  created_at: string;
  updated_at?: string;
  risk_level?: string;
}

interface AuditItem {
  audit_id: string;
  action: string;
  command: string;
  actor: string;
  device_id?: string;
}

const loading = ref(true);
const error = ref('');
const devices = ref<DeviceItem[]>([]);
const commands = ref<CommandItem[]>([]);
const audit = ref<AuditItem[]>([]);
const acting = ref(false);

const API = (import.meta.env.VITE_API_BASE_URL as string || 'http://127.0.0.1:8000').replace(/\/$/, '');

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const [dRes, cRes, aRes] = await Promise.all([
      fetch(`${API}/device/list/${encodeURIComponent(props.userId)}`),
      fetch(`${API}/device/commands?user_id=${encodeURIComponent(props.userId)}`),
      fetch(`${API}/device/audit?user_id=${encodeURIComponent(props.userId)}`),
    ]);
    if (dRes.ok) {
      const d = await dRes.json();
      devices.value = d.devices || [];
    }
    if (cRes.ok) {
      const c = await cRes.json();
      commands.value = c.commands || [];
    }
    if (aRes.ok) {
      const a = await aRes.json();
      audit.value = a.audit || [];
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function ping(d: DeviceItem) {
  acting.value = true;
  try {
    await fetch(`${API}/device/send_command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: props.userId, device_id: d.device_id, command: 'ping', payload: {} }),
    });
    await load();
  } finally {
    acting.value = false;
  }
}

async function sendTestNotify(d: DeviceItem) {
  acting.value = true;
  try {
    await fetch(`${API}/device/send_command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: props.userId,
        device_id: d.device_id,
        command: 'show_notification',
        payload: { title: '小暖', text: '这是来自小暖的测试通知 ✨' },
      }),
    });
    await load();
  } finally {
    acting.value = false;
  }
}

load();

function cmdIcon(s: string) {
  const map: Record<string, string> = {
    pending: '⏳',
    delivered: '📤',
    claimed: '📥',
    running: '🔄',
    succeeded: '✅',
    failed: '❌',
    denied: '⛔',
    timeout: '⏱️',
    cancelled: '🚫',
  };
  return map[s] || '•';
}

function statusLabel(s: string) {
  const map: Record<string, string> = {
    pending: '等待',
    delivered: '已下发',
    claimed: '已领取',
    running: '执行中',
    succeeded: '成功',
    failed: '失败',
    denied: '拒绝',
    timeout: '超时',
    cancelled: '已取消',
  };
  return map[s] || s;
}

function formatHb(iso: string) {
  try {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  } catch {
    return iso;
  }
}

function shortTime(iso: string) {
  try {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? '' : d.toLocaleTimeString();
  } catch {
    return '';
  }
}
</script>

<style scoped>
.task-section { margin-bottom: 20px; }
.task-section-title { font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 10px; padding-left: 4px; }

.device-card {
  background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 14px;
  padding: 12px 16px;
  margin-bottom: 8px;
}

.device-head { display: flex; align-items: center; gap: 8px; }
.online-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.online-dot.on { background: #4ade80; }
.online-dot.off { background: #64748b; }

.device-name { font-size: 14px; font-weight: 600; color: #e2e8f0; flex: 1; }
.tag { font-size: 10px; padding: 2px 8px; border-radius: 999px; }
.tag.on { color: #4ade80; background: rgba(74,222,128,0.1); }
.tag.off { color: #64748b; background: rgba(100,116,139,0.1); }

.device-meta { font-size: 11px; color: #64748b; margin-top: 4px; display: flex; gap: 8px; }
.device-caps { color: #818cf8; }

.device-actions { display: flex; gap: 6px; margin-top: 8px; }

.action-btn {
  font-size: 11px;
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid rgba(233, 69, 96, 0.16);
  background: rgba(233, 69, 96, 0.06);
  color: #f0f4ff;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover { background: rgba(233, 69, 96, 0.16); }
.action-btn:disabled { opacity: 0.4; }

.cmd-row { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 12px; }
.cmd-icon { width: 16px; }
.cmd-cmd { font-weight: 500; color: #94a3b8; min-width: 80px; }
.cmd-device { color: #64748b; flex: 1; }
.cmd-status { font-size: 10px; padding: 1px 6px; border-radius: 999px; }
.s-succeeded { color: #4ade80; background: rgba(74,222,128,0.1); }
.s-failed { color: #fca5a5; background: rgba(248,113,113,0.1); }
.s-pending, .s-delivered { color: #facc15; background: rgba(250,204,21,0.1); }
.s-claimed { color: #38bdf8; background: rgba(56,189,248,0.1); }
.s-running { color: #818cf8; background: rgba(129,140,248,0.1); }
.s-cancelled { color: #94a3b8; background: rgba(148,163,184,0.12); }

.device-heartbeat { font-size: 10px; color: #64748b; margin-top: 4px; }

.cmd-risk { font-size: 9px; text-transform: uppercase; color: #f472b6; margin-right: 4px; }
.cmd-updated { font-size: 10px; color: #64748b; margin-right: 4px; }

.audit-row { display: flex; align-items: center; gap: 8px; padding: 4px 8px; font-size: 11px; color: #94a3b8; border-bottom: 1px solid rgba(255,255,255,0.03); }
.audit-action { color: #818cf8; min-width: 72px; }
.audit-cmd { flex: 1; color: #64748b; }
.audit-actor { font-size: 10px; color: #475569; }

.status-box { padding: 20px; text-align: center; color: #94a3b8; font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 8px; }
.status-box.error { color: #fca5a5; }
.empty-state { text-align: center; padding: 24px; }
.empty-state p { color: #94a3b8; font-size: 13px; margin: 4px 0; }
.empty-hint { color: #64748b !important; font-size: 12px !important; margin-top: 8px !important; }
.spinner { width: 14px; height: 14px; border: 2px solid rgba(233,69,96,0.2); border-top-color: #e94560; border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
