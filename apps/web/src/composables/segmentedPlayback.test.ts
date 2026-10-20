import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import { createSegmentedPlayback } from './segmentedPlayback';

describe('segmented audio queue', () => {
  it('plays source order, skips failures, and ignores duplicates', async () => {
    const play = vi.fn(async (_url: string) => {}), end = vi.fn();
    const queue = createSegmentedPlayback({ play, stop: vi.fn(), allowed: () => true,
      onStart: vi.fn(), onEnd: end, onError: vi.fn() });
    queue.start();
    queue.put(2, '/two'); queue.put(0, '/zero'); queue.put(0, '/duplicate'); queue.put(1, null); queue.finish(3);
    await flushPromises();
    expect(play.mock.calls.map(call => call[0])).toEqual(['/zero', '/two']);
    expect(end).toHaveBeenCalledTimes(1);
  });

  it('does not play queued or late segments after cancellation', async () => {
    let complete!: () => void;
    const play = vi.fn(() => new Promise<void>(resolve => { complete = resolve; }));
    const queue = createSegmentedPlayback({ play, stop: vi.fn(), allowed: () => true,
      onStart: vi.fn(), onEnd: vi.fn(), onError: vi.fn() });
    queue.start(); queue.put(0, '/zero'); queue.put(1, '/one');
    queue.stop(); complete(); queue.put(2, '/late');
    await flushPromises();
    expect(play).toHaveBeenCalledTimes(1);
  });
});
