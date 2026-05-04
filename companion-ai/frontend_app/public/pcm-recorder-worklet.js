// AudioWorklet processor: down-mixes input to mono, accumulates frames,
// converts Float32 → Int16, posts ArrayBuffer to the main thread.
// Loaded via AudioWorkletNode("pcm-recorder").

class PcmRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    // Default chunk size: 2048 samples = ~128 ms @ 16 kHz target.
    this.frameBuffer = [];
    this.sampleAccum = 0;
    this.targetChunkSamples = 2048;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;

    // Mono — input from getUserMedia is already mono if requested.
    const buf = new Float32Array(channel.length);
    buf.set(channel);
    this.frameBuffer.push(buf);
    this.sampleAccum += buf.length;

    if (this.sampleAccum >= this.targetChunkSamples) {
      const merged = new Float32Array(this.sampleAccum);
      let offset = 0;
      for (const f of this.frameBuffer) {
        merged.set(f, offset);
        offset += f.length;
      }
      this.frameBuffer = [];
      this.sampleAccum = 0;

      const int16 = new Int16Array(merged.length);
      for (let i = 0; i < merged.length; i++) {
        const v = Math.max(-1, Math.min(1, merged[i]));
        int16[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-recorder', PcmRecorder);
