import { ref, computed } from 'vue';

export type ToolExecutionStatus = 'pending' | 'success' | 'error';

export interface ToolExecutionState {
  toolName: string;
  status: ToolExecutionStatus;
  message?: string;
  startTime: number;
  endTime?: number;
}

const TOOL_NAME_MAP: Record<string, string> = {
  weather: '查天气',
  search: '搜索',
  reminder: '设提醒',
  memory_recall: '回忆',
  memory_save: '记住',
  calculator: '计算',
  web_search: '网络搜索',
  image_search: '搜图片',
  news: '查新闻',
  translate: '翻译',
  calendar: '查日历',
  todo: '待办事项',
  default: '处理中',
};

function translateToolName(name: string): string {
  return TOOL_NAME_MAP[name] || name || '处理中';
}

/**
 * Lightweight tool-execution status tracker.
 *
 * Designed to be consumed by ChatMessage (per-message indicators) and
 * App.vue (global "current tool" banner above the input box).
 */
export function useToolStatus() {
  const currentTool = ref<ToolExecutionState | null>(null);
  const recentTools = ref<ToolExecutionState[]>([]);
  const maxHistory = 20;

  const isExecuting = computed(() => currentTool.value?.status === 'pending');
  const currentToolLabel = computed(() =>
    currentTool.value ? translateToolName(currentTool.value.toolName) : '',
  );

  function startTool(name: string, message?: string): void {
    const now = Date.now();
    // If there's an active pending tool, mark it as done first
    if (currentTool.value?.status === 'pending') {
      endTool(true, '被中断');
    }
    const state: ToolExecutionState = {
      toolName: name,
      status: 'pending',
      message,
      startTime: now,
    };
    currentTool.value = state;
  }

  function endTool(success: boolean, message?: string): void {
    if (!currentTool.value) return;
    const final: ToolExecutionState = {
      ...currentTool.value,
      status: success ? 'success' : 'error',
      message: message || currentTool.value.message,
      endTime: Date.now(),
    };
    currentTool.value = final;
    recentTools.value.push(final);
    if (recentTools.value.length > maxHistory) {
      recentTools.value.shift();
    }
  }

  function clearTool(): void {
    currentTool.value = null;
  }

  /** Call when a new assistant turn starts — clears stale tool state. */
  function resetForNewTurn(): void {
    clearTool();
  }

  return {
    currentTool,
    recentTools,
    isExecuting,
    currentToolLabel,
    startTool,
    endTool,
    clearTool,
    resetForNewTurn,
  };
}
