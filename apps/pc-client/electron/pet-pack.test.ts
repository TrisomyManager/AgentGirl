import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, symlink, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { readPetPack } from './pet-pack.ts';

test('source pack discovery preserves Chinese filenames and ignores links outside the selected pack', async () => {
  const root = await mkdtemp(join(process.cwd(), '.pet-test-'));
  try {
    await mkdir(join(root, 'videos', 'idle'), { recursive: true });
    await mkdir(join(root, 'videos', 'click'));
    await writeFile(join(root, 'videos', 'idle', '待机呼吸休闲.webm'), 'test');
    await writeFile(join(root, 'videos', 'click', '开心.webm'), 'test');
    await writeFile(join(root, 'videos', 'manifest.json'), JSON.stringify({ body_box: [212, 60, 428, 330] }));
    await writeFile(join(root, 'private.webm'), 'private');
    await symlink(join(root, 'private.webm'), join(root, 'videos', 'idle', 'outside.webm'));
    const pack = await readPetPack(root);
    assert.equal(pack.clips.length, 2);
    assert.ok(pack.clips.some(clip => clip.id === 'idle/待机呼吸休闲.webm'));
    assert.deepEqual(pack.bodyBox, [212, 60, 428, 330]);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('empty or unsupported frame-only packs report an explicit error', async () => {
  const root = await mkdtemp(join(process.cwd(), '.pet-test-'));
  try { await assert.rejects(readPetPack(root), /未找到 WebM/); }
  finally { await rm(root, { recursive: true, force: true }); }
});

test('invalid optional manifest values use safe defaults', async () => {
  const root = await mkdtemp(join(process.cwd(), '.pet-test-'));
  try {
    await writeFile(join(root, 'idle.webm'), 'test');
    for (const value of ['null', '[]', '42', '{broken']) {
      await writeFile(join(root, 'manifest.json'), value);
      const pack = await readPetPack(root);
      assert.deepEqual(pack.bodyBox, [0, 0, 640, 360]);
      assert.equal(pack.clips.length, 1);
    }
  } finally { await rm(root, { recursive: true, force: true }); }
});
