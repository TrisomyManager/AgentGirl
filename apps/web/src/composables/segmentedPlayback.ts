/** A bounded, cancellable queue; late callbacks never revive an older reply. */
export function createSegmentedPlayback(options: {
  play: (url: string) => Promise<void>;
  stop: () => void;
  allowed: () => boolean;
  onStart: (seq: number) => void;
  onEnd: () => void;
  onError: (message: string) => void;
}) {
  let generation = 0;
  let next = 0;
  let active = false;
  let running = false;
  let total: number | null = null;
  const pending = new Map<number, string | null>();

  function stop() {
    generation++;
    pending.clear();
    active = false;
    running = false;
    options.stop();
  }
  function start() { stop(); active = true; next = 0; total = null; }
  async function drain() {
    if (running || !active) return;
    if (!options.allowed()) { stop(); return; }
    running = true;
    const current = generation;
    try {
      while (active && generation === current && pending.has(next)) {
        const seq = next++;
        const url = pending.get(seq);
        pending.delete(seq);
        if (!url) continue;
        if (!options.allowed()) { stop(); return; }
        options.onStart(seq);
        try { await options.play(url); }
        catch { if (generation === current) options.onError('部分语音未能播放，可以稍后重听。'); }
      }
    } finally {
      if (generation === current) {
        running = false;
        if (total !== null && next >= total) { active = false; options.onEnd(); }
      }
    }
  }
  function put(seq: number, url: string | null) {
    if (!active || !Number.isInteger(seq) || seq < next || seq >= 256 || pending.has(seq)) return;
    pending.set(seq, url);
    void drain();
  }
  function finish(count: number) {
    if (!active || !Number.isInteger(count) || count < 0 || count > 256) return;
    total = count;
    for (let seq = next; seq < count; seq++) {
      if (!pending.has(seq)) pending.set(seq, null);
    }
    void drain();
  }
  return { start, put, finish, stop };
}
