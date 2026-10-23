/** dsh-pet source character-pack compatibility, independent of Electron/Qt. */
import { readdir, readFile, realpath, stat } from 'node:fs/promises';
import { basename, extname, join, relative, sep } from 'node:path';

export interface PetClip { id: string; name: string; group: string; path: string }
export interface PetPack {
  name: string;
  root: string;
  width: number;
  height: number;
  bodyBox: number[];
  clips: PetClip[];
}

const GROUPS = new Set(['idle', 'idle_turn', 'turn', 'move', 'click', 'drag', 'random', 'events']);

export async function readPetPack(directory: string): Promise<PetPack> {
  let root = await realpath(directory);
  try { if ((await stat(join(root, 'videos'))).isDirectory()) root = await realpath(join(root, 'videos')); }
  catch { /* Already a videos folder. */ }
  let manifest: Record<string, unknown> = {};
  try {
    const value: unknown = JSON.parse(await readFile(join(root, 'manifest.json'), 'utf8'));
    if (value && typeof value === 'object' && !Array.isArray(value)) manifest = value as Record<string, unknown>;
  }
  catch { /* Manifest is optional in legacy dsh-pet source packs. */ }
  const clips: PetClip[] = [];
  async function walk(folder: string, group: string, depth: number) {
    if (depth > 3) return;
    const entries = await readdir(folder, { withFileTypes: true });
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isSymbolicLink()) continue;
      const file = join(folder, entry.name);
      if (entry.isDirectory() && (depth > 0 || GROUPS.has(entry.name))) {
        await walk(file, depth === 0 ? entry.name : group, depth + 1);
      } else if (entry.isFile() && ['.webm', '.gif'].includes(extname(entry.name).toLowerCase())) {
        const resolved = await realpath(file);
        if (relative(root, resolved).startsWith(`..${sep}`)) continue;
        const id = relative(root, resolved).split(sep).join('/');
        clips.push({ id, name: basename(entry.name, extname(entry.name)), group: group || 'idle', path: resolved });
        if (clips.length > 512) throw new Error('素材包动作超过 512 段，请选择单个角色目录');
      }
    }
  }
  await walk(root, '', 0);
  if (!clips.length) throw new Error('未找到 WebM/GIF。请选择 dsh-pet 的角色或 videos 目录；纯帧序列包暂不支持。');
  const box = manifest.body_box;
  const bodyBox = Array.isArray(box) && box.length === 4 && box.every(n => typeof n === 'number' && Number.isFinite(n))
    && box[0] >= 0 && box[1] >= 0 && box[2] <= 640 && box[3] <= 360 && box[2] > box[0] && box[3] > box[1]
    ? box as number[] : [0, 0, 640, 360];
  return { name: typeof manifest.name === 'string' ? manifest.name.slice(0, 80) : basename(directory),
    root, width: 640, height: 360, bodyBox, clips };
}
