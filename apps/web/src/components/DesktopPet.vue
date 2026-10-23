<template>
  <main class="pet-surface" @contextmenu.prevent="bridge?.menu()">
    <div v-if="bubble" class="pet-bubble" role="status">{{ bubble }}</div>
    <div class="pet-actor" @pointerdown="beginDrag" @pointermove="drag" @pointerup="endDrag"
      @pointercancel="cancelDrag" @lostpointercapture="cancelDrag" @dblclick="bridge?.menu()">
      <img v-if="clip?.id.toLowerCase().endsWith('.gif')" :src="clip.url" alt="陪伴角色" draggable="false" />
      <video v-else-if="clip" :key="clip.url" :src="clip.url" autoplay muted playsinline
        :loop="looping" @ended="idle" @error="playError" />
      <div v-else class="pet-placeholder" aria-label="默认陪伴角色">🌷</div>
    </div>
    <p v-if="error" class="pet-error">{{ error }}</p>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { PetClip, PetPack } from '../composables/desktopBridge';

interface PetAPI {
  status(): Promise<{ pack: PetPack | null }>;
  move(dx: number, dy: number): Promise<void>;
  dragEnd(): Promise<void>;
  menu(): Promise<void>;
  onPack(callback: (pack: PetPack) => void): () => void;
  onBubble(callback: (bubble: { text: string; emotion: string }) => void): () => void;
}
const bridge = (window as unknown as { petAPI?: PetAPI }).petAPI;
const pack = ref<PetPack | null>(null);
const clip = ref<PetClip | null>(null);
const bubble = ref('');
const error = ref('');
const looping = computed(() => ['idle', 'idle_turn'].includes(clip.value?.group ?? 'idle'));
let pointer: { id: number; x: number; y: number; total: number } | null = null;
let bubbleTimer: ReturnType<typeof setTimeout> | undefined;
const unsubscribe: Array<() => void> = [];

function play(group: string) {
  const choices = pack.value?.clips.filter(item => item.group === group) ?? [];
  if (choices.length) clip.value = choices[Math.floor(Math.random() * choices.length)];
  else if (group !== 'idle') idle();
}
function idle() {
  clip.value = pack.value?.clips.find(item => item.group === 'idle')
    ?? pack.value?.clips.find(item => item.group === 'idle_turn') ?? pack.value?.clips[0] ?? null;
}
function beginDrag(event: PointerEvent) {
  if (event.button !== 0) return;
  pointer = { id: event.pointerId, x: event.screenX, y: event.screenY, total: 0 };
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}
function drag(event: PointerEvent) {
  if (!pointer || pointer.id !== event.pointerId) return;
  const dx = event.screenX - pointer.x, dy = event.screenY - pointer.y;
  pointer.x = event.screenX; pointer.y = event.screenY;
  pointer.total += Math.abs(dx) + Math.abs(dy);
  if (pointer.total > 4) {
    if (clip.value?.group !== 'drag') play('drag');
    void bridge?.move(Math.max(-100, Math.min(100, dx)), Math.max(-100, Math.min(100, dy)));
  }
}
function endDrag(event: PointerEvent) {
  if (!pointer || pointer.id !== event.pointerId) return;
  const clicked = pointer.total <= 4;
  pointer = null;
  void bridge?.dragEnd();
  if (clicked) play('click'); else idle();
}
function cancelDrag() { if (pointer) { pointer = null; void bridge?.dragEnd(); idle(); } }
function playError() { error.value = '素材播放失败，请更换 WebM/GIF 素材包'; clip.value = null; }
function setPack(value: PetPack | null) { pack.value = value; error.value = ''; idle(); }
onMounted(async () => {
  if (!bridge) return;
  unsubscribe.push(bridge.onPack(setPack), bridge.onBubble(value => {
    bubble.value = value.text;
    if (bubbleTimer) clearTimeout(bubbleTimer);
    bubbleTimer = setTimeout(() => { bubble.value = ''; }, 10000);
    play('click');
  }));
  try { setPack((await bridge.status()).pack); } catch { error.value = '暂时无法加载桌宠'; }
});
onUnmounted(() => { unsubscribe.forEach(stop => stop()); if (bubbleTimer) clearTimeout(bubbleTimer); });
</script>

<style>
html, body, #app { margin: 0; width: 100%; height: 100%; background: transparent !important; overflow: hidden; }
.pet-surface { position: relative; height: 100%; user-select: none; font: 14px/1.5 system-ui, sans-serif; }
.pet-actor { position: absolute; inset: 70px 0 0; cursor: grab; touch-action: none; }
.pet-actor:active { cursor: grabbing; }
.pet-actor video, .pet-actor img { width: 100%; height: 100%; object-fit: contain; pointer-events: none; }
.pet-placeholder { font-size: 100px; text-align: center; padding-top: 40px; }
.pet-bubble { position: absolute; inset: 4px 20px auto; max-height: 95px; overflow: auto; border-radius: 18px;
  padding: 12px 16px; background: #fff7ef; color: #513a33; box-shadow: 0 4px 18px #0002; }
.pet-error { position: absolute; bottom: 0; padding: 5px 12px; color: #862f24; background: #fff7ef; border-radius: 12px; }
</style>
