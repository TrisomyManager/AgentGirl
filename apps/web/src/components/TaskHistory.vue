<template>
  <section class="task-history" aria-label="多步任务">
    <div class="history-heading"><strong>任务进度</strong><button type="button" @click="load">刷新</button></div>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="!tasks.length && !error" class="hint">可以试试：“先告诉我现在几点，再在十分钟后提醒我休息”。</p>
    <article v-for="task in tasks" :key="task.id" class="run-card">
      <div class="run-heading"><span>{{ task.request }}</span><b>{{ statusLabel(task.status) }}</b></div>
      <ol v-if="task.steps.length">
        <li v-for="step in task.steps" :key="step.position">
          {{ toolLabel(step.tool_name) }} · {{ statusLabel(step.status) }}
          <p v-if="step.result.message">{{ step.result.message }}</p>
        </li>
      </ol>
      <p v-if="task.message" class="run-message">{{ task.message }}</p>
      <button v-if="['running', 'awaiting_input'].includes(task.status)" type="button" :disabled="busy === task.id" @click="cancel(task.id)">停止任务</button>
      <form v-if="task.status === 'awaiting_input'" @submit.prevent="resume(task.id)">
        <label :for="`clarify-${task.id}`">补充信息</label>
        <input :id="`clarify-${task.id}`" v-model="clarifications[task.id]" required maxlength="2000" :disabled="busy === task.id" />
        <button type="submit" :disabled="busy === task.id">{{ busy === task.id ? '继续执行中…' : '继续任务' }}</button>
      </form>
    </article>
  </section>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import { useApi, type TaskRun } from '../composables/useApi';

const props = defineProps<{ userId: string }>();
const emit = defineEmits<{ (event: 'changed'): void }>();
const { getTasks, cancelTask, resumeTask } = useApi();
const tasks = ref<TaskRun[]>([]);
const error = ref('');
const busy = ref('');
const clarifications = ref<Record<string, string>>({});
let generation = 0;
let disposed = false;
let timer: ReturnType<typeof setTimeout> | null = null;
let requestIndex = 0;

const labels: Record<string, string> = {
  running: '执行中', awaiting_input: '等待补充', completed: '已完成', failed: '执行失败', interrupted: '已中断',
  cancelled: '已停止', limit_reached: '已到步骤上限', success: '已完成', error: '执行失败', outcome_unknown: '需要核对结果',
};
const tools: Record<string, string> = {
  get_time: '查看时间', get_weather: '查询天气', web_search: '搜索', query_memory: '回忆',
  set_reminder: '创建提醒', cancel_reminder: '取消提醒', list_reminders: '查看提醒', timer_countdown: '设置计时',
  update_user_profile: '更新资料', list_devices: '查看设备', device_ping: '检查设备', device_notify: '发送通知', device_open_url: '打开网页',
};
function statusLabel(status: string) { return labels[status] || '处理中'; }
function toolLabel(tool: string) { return tools[tool] || '扩展工具'; }

async function load() {
  if (timer) clearTimeout(timer);
  const user = props.userId;
  const current = generation;
  const index = ++requestIndex;
  try {
    const result = await getTasks(user);
    if (disposed || current !== generation || index !== requestIndex) return;
    tasks.value = result;
    error.value = '';
    if (result.some(task => task.status === 'running')) timer = setTimeout(load, 3000);
  } catch {
    if (!disposed && current === generation && index === requestIndex) error.value = '读取任务失败，请刷新重试。';
  }
}

async function act(taskId: string, operation: (user: string) => Promise<void>) {
  const current = generation;
  const user = props.userId;
  busy.value = taskId;
  error.value = '';
  try {
    await operation(user);
    if (!disposed && current === generation) { await load(); emit('changed'); }
  } catch (err) {
    if (!disposed && current === generation) error.value = err instanceof Error ? err.message : '任务操作失败。';
  } finally {
    if (!disposed && current === generation) busy.value = '';
  }
}
async function cancel(taskId: string) { await act(taskId, user => cancelTask(taskId, user)); }
async function resume(taskId: string) {
  const clarification = (clarifications.value[taskId] || '').trim();
  if (clarification) await act(taskId, user => resumeTask(taskId, user, clarification));
}

watch(() => props.userId, () => {
  generation++;
  tasks.value = [];
  clarifications.value = {};
  error.value = '';
  busy.value = '';
  void load();
}, { immediate: true });
onUnmounted(() => { disposed = true; generation++; if (timer) clearTimeout(timer); });
</script>

<style scoped>
.task-history { margin-bottom: 22px; font-size: 13px; color: #e2e8f0; }
.history-heading, .run-heading { display: flex; justify-content: space-between; gap: 12px; align-items: start; }
.hint { color: #94a3b8; line-height: 1.6; }
.run-card { margin-top: 12px; padding: 12px; border: 1px solid rgba(148, 163, 184, .2); border-radius: 12px; background: rgba(255, 255, 255, .03); }
.run-heading span { overflow-wrap: anywhere; white-space: pre-wrap; flex: 1; min-width: 0; }
.run-heading b { white-space: nowrap; color: #c4b5fd; }
.run-message, li p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.6; }
ol { padding-left: 20px; }
li p { color: #aebbd0; margin: 4px 0 8px; }
button { border: 1px solid rgba(148, 163, 184, .3); border-radius: 7px; background: #25283a; padding: 5px 9px; cursor: pointer; color: #e2e8f0; }
button:disabled { opacity: .6; cursor: wait; }
form { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; align-items: center; }
input { flex: 1; min-width: 120px; border: 1px solid rgba(148, 163, 184, .3); border-radius: 6px; padding: 6px; color: #e2e8f0; background: #1c2230; }
</style>
