// @vitest-environment node
import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('bundled Live2D model', () => {
  it('ships every referenced model, texture, animation and sound as a real file', () => {
    const root = resolve('public/live2d/shizuku');
    const model = JSON.parse(readFileSync(resolve(root, 'shizuku.model.json'), 'utf8'));
    const files = new Set<string>([model.model, model.physics, model.pose, ...model.textures]);
    model.expressions.forEach((entry: { file: string }) => files.add(entry.file));
    Object.values(model.motions).forEach((group) => {
      (group as { file: string; sound?: string }[]).forEach((entry) => {
        files.add(entry.file);
        if (entry.sound) files.add(entry.sound);
      });
    });
    for (const file of files) {
      const path = resolve(root, file);
      expect(statSync(path).size, file).toBeGreaterThan(0);
      const content = readFileSync(path);
      if (file.endsWith('.moc')) expect(content.subarray(0, 3).toString(), file).toBe('moc');
      if (file.endsWith('.png')) expect(content.subarray(0, 8).toString('hex'), file).toBe('89504e470d0a1a0a');
      if (file.endsWith('.json')) expect(() => JSON.parse(content.toString()), file).not.toThrow();
    }
  });
});
