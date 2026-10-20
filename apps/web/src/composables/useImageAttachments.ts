import { onBeforeUnmount, ref } from 'vue';

export interface ImageAttachment { name: string; size: number; url: string }
const MIB = 1024 * 1024;

export function useImageAttachments() {
  const images = ref<ImageAttachment[]>([]);
  const error = ref('');
  const reading = ref(false);
  const readers = new Set<FileReader>();
  let generation = 0;

  function clear() {
    generation++;
    for (const reader of readers) reader.abort();
    readers.clear();
    reading.value = false;
    images.value = [];
    error.value = '';
  }
  onBeforeUnmount(clear);

  async function select(files: File[]) {
    if (reading.value || !files.length) return;
    error.value = '';
    if (files.length + images.value.length > 3) { error.value = '每次最多发送 3 张图片。'; return; }
    if (files.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) {
      error.value = '请选择 JPEG、PNG 或 WebP 图片。'; return;
    }
    if (files.some(file => !file.size || file.size > 5 * MIB)) { error.value = '每张图片应大于 0 且不能超过 5 MiB。'; return; }
    if ([...files, ...images.value].reduce((sum, file) => sum + file.size, 0) > 10 * MIB) {
      error.value = '图片总大小不能超过 10 MiB。'; return;
    }
    const epoch = ++generation;
    reading.value = true;
    try {
      const selected = await Promise.all(files.map(file => new Promise<ImageAttachment>((resolve, reject) => {
        const reader = new FileReader();
        readers.add(reader);
        reader.onload = () => resolve({ name: file.name, size: file.size, url: String(reader.result) });
        reader.onerror = () => reject(new Error('图片读取失败，请重新选择。'));
        reader.onabort = () => reject(new Error('图片读取已取消。'));
        reader.onloadend = () => readers.delete(reader);
        reader.readAsDataURL(file);
      })));
      if (epoch === generation) images.value.push(...selected);
    } catch (err) {
      if (epoch === generation) error.value = err instanceof Error ? err.message : '图片读取失败。';
    } finally {
      if (epoch === generation) reading.value = false;
    }
  }
  return { images, error, reading, select, clear };
}
