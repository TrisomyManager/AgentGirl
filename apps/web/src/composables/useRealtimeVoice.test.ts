import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
import { flushPromises } from '@vue/test-utils';
import { avatarFrame } from './useAvatarPresentation';
import { encodeAudioFrame } from '../../../../packages/audio-transport/src';
import {
  currentAudioFormat,
  currentRealtimeProvider,
  currentSampleRate,
  useRealtimeVoice,
} from './useRealtimeVoice';

const vadState = vi.hoisted(() => ({ callbacks: null as any }));
vi.mock('@ricky0123/vad-web', () => ({ MicVAD: { new: async (options: any) => {
  vadState.callbacks = options;
  return { start: vi.fn(), pause: vi.fn(), destroy: vi.fn() };
} } }));

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function buildFakeWebSocket(protocol: 'raw' | 'framed-v1' | 'none' = 'raw') {
  let instance: any = null;

  const origWS = globalThis.WebSocket;
  const MockWS = vi.fn(function (this: any, _url: string) {
    this.readyState = WebSocket.OPEN;
    this.binaryType = 'arraybuffer';
    this.url = '';
    this.send = vi.fn();
    this.close = vi.fn(() => { this.readyState = 3; queueMicrotask(() => this.onclose?.({ code: 1000 })); });
    this.onopen = null;
    this.onerror = null;
    this.onclose = null;
    this.onmessage = null;
    instance = this;
    // Fire onopen on next microtask so startCall() resolves
    queueMicrotask(() => {
      if (this.onopen) this.onopen({} as Event);
      if (protocol !== 'none') this.onmessage?.({ data: JSON.stringify(protocol === 'raw' ? { type: 'ready' } : {
        type: 'transport_ready', audio_protocol: protocol,
      }) });
    });
    return this;
  }) as any;
  MockWS.OPEN = 1;
  MockWS.CONNECTING = 0;
  globalThis.WebSocket = MockWS;

  return {
    fireControl(msg: Record<string, unknown>) {
      if (instance && instance.onmessage) {
        instance.onmessage({ data: JSON.stringify(msg) } as MessageEvent);
      }
    },
    fireAudioChunk(buf: ArrayBuffer) {
      if (instance && instance.onmessage) {
        instance.onmessage({ data: buf } as MessageEvent);
      }
    },
    restore: () => {
      globalThis.WebSocket = origWS;
    },
  };
}

function buildMockAudioContext() {
  const createBuffer = vi.fn((channels: number, length: number, sampleRate: number) => ({
    duration: length / sampleRate,
    numberOfChannels: channels,
    sampleRate,
    length,
    getChannelData: vi.fn(() => new Float32Array(length)),
    copyFromChannel: vi.fn(),
    copyToChannel: vi.fn(),
  })) as any as typeof AudioContext.prototype.createBuffer;

  const mockSource = {
    buffer: null as AudioBuffer | null,
    start: vi.fn(),
    stop: vi.fn(),
    connect: vi.fn(),
    onended: null as (() => void) | null,
  };
  const createBufferSource = vi.fn(() => mockSource);
  const decodeAudioData = vi.fn((_buf: ArrayBuffer) =>
    Promise.resolve({
      duration: 0.5,
      numberOfChannels: 1,
      sampleRate: 24000,
      length: 0,
      getChannelData: vi.fn(() => new Float32Array(0)),
      copyFromChannel: vi.fn(),
      copyToChannel: vi.fn(),
    })
  );
  const destination = {} as AudioNode;

  const ctx = {
    currentTime: 100,
    sampleRate: 24000,
    destination,
    createBufferSource,
    createBuffer,
    decodeAudioData,
    resume: vi.fn(() => Promise.resolve()),
    close: vi.fn(() => Promise.resolve()),
    createMediaStreamSource: vi.fn(() => ({
      connect: vi.fn(),
      disconnect: vi.fn(),
    })),
    createGain: vi.fn(() => ({ gain: { value: 1 }, connect: vi.fn() })),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    audioWorklet: {
      addModule: vi.fn(() => Promise.resolve()),
    },
  } as any as AudioContext;

  return { ctx, mockSource, createBufferSource, createBuffer, decodeAudioData };
}

function installAudioContextMock() {
  (globalThis as any).AudioContext = (globalThis as any).webkitAudioContext = class {};
  if (typeof (globalThis as any).AudioWorkletNode === 'undefined') {
    (globalThis as any).AudioWorkletNode = class {
      port = { onmessage: null, postMessage: vi.fn() };
      connect(_node: any) {}
      disconnect() {}
    };
  }
}

function mockAudioContext(ctx: AudioContext) {
  vi.spyOn(globalThis, 'AudioContext' as any).mockImplementation(class {
    constructor() { return ctx; }
  } as any);
}

function installMediaMock() {
  // jsdom has no navigator.mediaDevices; stub it
  const mockStream = {
    getTracks: () => [],
    addTrack: vi.fn(),
    removeTrack: vi.fn(),
  };
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    value: {
      getUserMedia: vi.fn(() => Promise.resolve(mockStream)),
    },
    configurable: true,
    writable: true,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('realtime playback lifecycle', () => {
  beforeEach(() => { installAudioContextMock(); installMediaMock(); });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('settles cancellation during protocol negotiation without opening the microphone', async () => {
    const ws = buildFakeWebSocket('none');
    const call = useRealtimeVoice();
    const starting = call.startCall(); await flushPromises();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    await call.stopCall(); await starting;
    expect(call.state.value).toBe('idle');
    ws.restore();
  });

  it('releases microphone tracks on fatal errors before another call starts', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext(), stop = vi.fn();
    mockAudioContext(mock.ctx);
    vi.mocked(navigator.mediaDevices.getUserMedia).mockResolvedValue({ getTracks: () => [{ stop }] } as any);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'error', msg: '连接失败' });
    await flushPromises();
    expect(stop).toHaveBeenCalledTimes(1);
    expect(call.state.value).toBe('error');
    expect(call.errorMsg.value).toBe('连接失败');
    await call.startCall();
    expect(call.state.value).toBe('listening');
    await call.stopCall(); ws.restore();
  });

  it('applies the control size limit in UTF-8 bytes', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_text_delta', text: '汉'.repeat(22000) });
    await flushPromises();
    expect(call.state.value).toBe('error');
    expect(call.partialAssistant.value).toBe('');
    await call.stopCall(); ws.restore();
  });

  it('plays only the active framed stream and rejects duplicated packet sequences', async () => {
    const ws = buildFakeWebSocket('framed-v1'), mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'pcm', sample_rate: 24000, audio_stream_id: 1 });
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'pcm', sample_rate: 24000, audio_stream_id: 2 });
    ws.fireAudioChunk(encodeAudioFrame(new ArrayBuffer(4800), 1, 0));
    expect(mock.createBuffer).not.toHaveBeenCalled();
    ws.fireAudioChunk(encodeAudioFrame(new ArrayBuffer(4800), 2, 1));
    expect(mock.createBuffer).toHaveBeenCalledTimes(1);
    ws.fireAudioChunk(encodeAudioFrame(new ArrayBuffer(4800), 2, 1));
    expect(call.state.value).toBe('error');
    expect(call.errorMsg.value).toContain('顺序不正确');
    await call.stopCall(); ws.restore();
  });

  it('keeps sentence expressions attached to their decoded audio and stops mouth frames on hangup', async () => {
    let tick!: FrameRequestCallback;
    vi.stubGlobal('requestAnimationFrame', vi.fn(callback => { tick = callback; return 1; }));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);
    let decode!: (buffer: any) => void;
    mock.decodeAudioData.mockImplementation(() => new Promise(resolve => { decode = resolve; }));
    const call = useRealtimeVoice(); await call.startCall();
    const timeline = (seq: number, emotion: string) => ({ version: 1, turn_id: 't', segment_seq: seq,
      duration_ms: null, clock: 'audio_playback', mouth_source: 'audio_rms',
      cues: [{ offset_ms: 0, emotion, intensity: .8, gesture: 'idle' }] });
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'mp3', avatar_timeline: timeline(0, 'happy') });
    ws.fireAudioChunk(new ArrayBuffer(16));
    // Metadata for the next sentence arrives before the first decode completes.
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'mp3', avatar_timeline: timeline(1, 'sad') });
    decode({ duration: .5, sampleRate: 24000, getChannelData: () => new Float32Array(12000).fill(.25) });
    await flushPromises();
    expect(avatarFrame.value.active).toBe(false);
    Object.defineProperty(mock.ctx, 'currentTime', { value: 100.15, writable: true });
    tick(150);
    expect(avatarFrame.value.emotion).toBe('happy');
    expect(avatarFrame.value.mouthOpen).toBeGreaterThan(.5);
    await call.stopCall();
    tick(250);
    expect(avatarFrame.value.active).toBe(false);
    expect(avatarFrame.value.mouthOpen).toBe(0);
    ws.restore();
  });

  it('releases a late microphone permission result after the user has ended the call', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);
    let grant!: (value: any) => void;
    const stop = vi.fn();
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(() => new Promise(resolve => { grant = resolve; }));
    const call = useRealtimeVoice();
    const starting = call.startCall(); await flushPromises();
    await call.stopCall(); grant({ getTracks: () => [{ stop }] }); await starting;
    expect(stop).toHaveBeenCalledTimes(1);
    expect(call.state.value).toBe('idle');
    ws.restore();
  });

  it('drops compressed audio decoded after interruption', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    let decode!: (buffer: any) => void;
    mock.decodeAudioData.mockImplementation(() => new Promise(resolve => { decode = resolve; }));
    mockAudioContext(mock.ctx);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'mp3' });
    ws.fireAudioChunk(new ArrayBuffer(16));
    ws.fireControl({ type: 'interrupted' });
    decode({ duration: .5 }); await flushPromises();
    expect(mock.createBufferSource).not.toHaveBeenCalled();
    await call.stopCall(); ws.restore();
  });

  it('joins split PCM samples and clears a half sample on interruption', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'pcm', sample_rate: 16000 });
    ws.fireAudioChunk(new Uint8Array([0]).buffer);
    expect(mock.createBuffer).not.toHaveBeenCalled();
    ws.fireAudioChunk(new Uint8Array([32]).buffer);
    expect(mock.createBuffer).toHaveBeenCalledWith(1, 1, 16000);
    ws.fireAudioChunk(new Uint8Array([1]).buffer);
    ws.fireControl({ type: 'interrupted' });
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'pcm', sample_rate: 16000 });
    ws.fireAudioChunk(new Uint8Array([0]).buffer);
    expect(mock.createBuffer).toHaveBeenCalledTimes(1);
    await call.stopCall(); ws.restore();
  });

  it('waits for the actual playback end after generation finishes', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'pcm' });
    ws.fireControl({ type: 'assistant_text_delta', text: '回答内容' });
    ws.fireAudioChunk(new ArrayBuffer(16));
    ws.fireControl({ type: 'turn_done' });
    expect(call.state.value).toBe('speaking');
    expect(call.transcript.value.slice(-1)[0]?.text).toBe('回答内容');
    mock.mockSource.onended!();
    expect(call.state.value).toBe('listening');
    await call.stopCall(); ws.restore();
  });

  it('preserves compressed chunk order when the second decode finishes first', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    const resolve: ((value: any) => void)[] = [];
    mock.decodeAudioData.mockImplementation(() => new Promise(done => { resolve.push(done); }));
    mockAudioContext(mock.ctx);
    const buffers: any[] = [];
    mock.createBufferSource.mockImplementation(() => {
      const source = { start: vi.fn(), stop: vi.fn(), connect: vi.fn(), onended: null } as any;
      Object.defineProperty(source, 'buffer', { set: value => buffers.push(value) });
      return source;
    });
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'mp3' });
    ws.fireAudioChunk(new ArrayBuffer(8)); ws.fireAudioChunk(new ArrayBuffer(8));
    const first = { duration: .1, marker: 'first' }, second = { duration: .2, marker: 'second' };
    resolve[1](second); await flushPromises(); expect(buffers).toEqual([]);
    resolve[0](first); await flushPromises(); expect(buffers).toEqual([first, second]);
    await call.stopCall(); ws.restore();
  });

  it('bounds pending decodes and discards their late results after overload', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    const resolve: ((value: any) => void)[] = [];
    mock.decodeAudioData.mockImplementation(() => new Promise(done => { resolve.push(done); }));
    mockAudioContext(mock.ctx);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'mp3' });
    for (let i = 0; i < 17; i++) ws.fireAudioChunk(new ArrayBuffer(8));
    expect(mock.decodeAudioData).toHaveBeenCalledTimes(16);
    expect(call.errorMsg.value).toContain('语音积压过多');
    expect(call.state.value).toBe('listening');
    resolve.forEach(done => done({ duration: .1 })); await flushPromises();
    expect(mock.createBufferSource).not.toHaveBeenCalled();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'mp3' });
    ws.fireAudioChunk(new ArrayBuffer(8));
    resolve[16]({ duration: .1 }); await flushPromises();
    expect(mock.createBufferSource).toHaveBeenCalledTimes(1);
    await call.stopCall(); ws.restore();
  });

  it('includes the incoming buffer in the playback limit and recovers on the next sentence', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'pcm', sample_rate: 16000 });
    ws.fireAudioChunk(new ArrayBuffer(16000 * 2 * 20));
    ws.fireAudioChunk(new ArrayBuffer(16000 * 2 * 11));
    expect(mock.createBufferSource).toHaveBeenCalledTimes(1);
    expect(mock.mockSource.stop).toHaveBeenCalledTimes(1);
    expect(call.state.value).toBe('listening');
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'pcm' });
    ws.fireAudioChunk(new ArrayBuffer(8));
    expect(mock.createBufferSource).toHaveBeenCalledTimes(2);
    await call.stopCall(); ws.restore();
  });

  it('rejects oversized frames before decoding and normalizes an invalid sample rate', async () => {
    const ws = buildFakeWebSocket(), mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);
    const call = useRealtimeVoice(); await call.startCall();
    ws.fireControl({ type: 'assistant_sentence_start', audio_format: 'mp3', sample_rate: -1 });
    expect(currentSampleRate.value).toBe(22050);
    ws.fireAudioChunk(new ArrayBuffer(2 * 1024 * 1024 + 1));
    expect(mock.decodeAudioData).not.toHaveBeenCalled();
    expect(call.errorMsg.value).toContain('语音积压过多');
    await call.stopCall(); ws.restore();
  });
});

describe('useRealtimeVoice – audio_format state', () => {
  beforeEach(() => {
    currentAudioFormat.value = 'pcm';
    currentRealtimeProvider.value = '';
    currentSampleRate.value = 0;
    installAudioContextMock();
    installMediaMock();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('默认 audio_format 为 pcm', () => {
    expect(currentAudioFormat.value).toBe('pcm');
  });

  it('assistant_sentence_start 解析 audio_format、sample_rate、provider', async () => {
    const ws = buildFakeWebSocket();
    const mockAudioCtx = buildMockAudioContext();
    mockAudioContext(mockAudioCtx.ctx);

    const { startCall, stopCall } = useRealtimeVoice();
    await startCall();
    await nextTick();
    ws.fireControl({ type: 'ready' });

    ws.fireControl({
      type: 'assistant_sentence_start',
      audio_format: 'opus',
      sample_rate: 48000,
      provider: 'openai_realtime',
    });

    expect(currentAudioFormat.value).toBe('opus');
    expect(currentSampleRate.value).toBe(48000);
    expect(currentRealtimeProvider.value).toBe('openai_realtime');

    void stopCall();
    ws.restore();
  });

  it('assistant_sentence_start 缺省字段回退到默认值', async () => {
    const ws = buildFakeWebSocket();
    mockAudioContext(buildMockAudioContext().ctx);

    const { startCall } = useRealtimeVoice();
    await startCall();
    await nextTick();
    ws.fireControl({ type: 'ready' });

    ws.fireControl({
      type: 'assistant_sentence_start',
      sample_rate: 22050,
    });

    expect(currentAudioFormat.value).toBe('pcm');
    expect(currentSampleRate.value).toBe(22050);
    expect(currentRealtimeProvider.value).toBe('');

    ws.restore();
  });

  it('tts_start 也同步更新模块级状态', async () => {
    const ws = buildFakeWebSocket();
    mockAudioContext(buildMockAudioContext().ctx);

    const { startCall } = useRealtimeVoice();
    await startCall();
    await nextTick();
    ws.fireControl({ type: 'ready' });

    ws.fireControl({
      type: 'tts_start',
      audio_format: 'mp3',
      sample_rate: 44100,
      provider: 'dashscope',
    });

    expect(currentAudioFormat.value).toBe('mp3');
    expect(currentSampleRate.value).toBe(44100);
    expect(currentRealtimeProvider.value).toBe('dashscope');

    ws.restore();
  });
});

describe('useRealtimeVoice – audio_format branch routing', () => {
  beforeEach(() => {
    currentAudioFormat.value = 'pcm';
    currentSampleRate.value = 24000;
    currentRealtimeProvider.value = '';
    installAudioContextMock();
    installMediaMock();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('pcm 格式走 Int16→Float32→createBuffer 路径，不调 decodeAudioData', async () => {
    const ws = buildFakeWebSocket();
    const mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);

    const { startCall } = useRealtimeVoice();
    await startCall();
    await nextTick();
    ws.fireControl({ type: 'ready' });
    ws.fireControl({
      type: 'assistant_sentence_start',
      audio_format: 'pcm',
      sample_rate: 24000,
      provider: 'test_provider',
    });

    const int16 = new Int16Array([0x2000, -0x1000]);
    const buf = int16.buffer;
    ws.fireAudioChunk(buf);

    await nextTick();
    await nextTick();

    expect(mock.createBuffer).toHaveBeenCalled();
    expect(mock.createBufferSource).toHaveBeenCalled();
    expect(mock.decodeAudioData).not.toHaveBeenCalled();
    expect(mock.mockSource.start).toHaveBeenCalled();

    ws.restore();
  });

  it('opus 格式走 decodeAudioData 路径', async () => {
    const ws = buildFakeWebSocket();
    const mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);

    const { startCall } = useRealtimeVoice();
    await startCall();
    await nextTick();
    ws.fireControl({ type: 'ready' });
    ws.fireControl({
      type: 'assistant_sentence_start',
      audio_format: 'opus',
      sample_rate: 48000,
      provider: 'openai_realtime',
    });

    const buf = new ArrayBuffer(16);
    ws.fireAudioChunk(buf);
    await nextTick();
    await nextTick();

    expect(mock.decodeAudioData).toHaveBeenCalled();
    expect(mock.createBuffer).not.toHaveBeenCalled();

    ws.restore();
  });

  it('mp3 格式走 decodeAudioData 路径', async () => {
    const ws = buildFakeWebSocket();
    const mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);

    const { startCall } = useRealtimeVoice();
    await startCall();
    await nextTick();
    ws.fireControl({ type: 'ready' });
    ws.fireControl({
      type: 'assistant_sentence_start',
      audio_format: 'mp3',
      sample_rate: 44100,
      provider: 'dashscope',
    });

    const buf = new ArrayBuffer(32);
    ws.fireAudioChunk(buf);
    await nextTick();
    await nextTick();

    expect(mock.decodeAudioData).toHaveBeenCalled();
    expect(mock.createBuffer).not.toHaveBeenCalled();

    ws.restore();
  });

  it('未知格式也走 decodeAudioData 路径', async () => {
    const ws = buildFakeWebSocket();
    const mock = buildMockAudioContext();
    mockAudioContext(mock.ctx);

    const { startCall } = useRealtimeVoice();
    await startCall();
    await nextTick();
    ws.fireControl({ type: 'ready' });
    ws.fireControl({
      type: 'assistant_sentence_start',
      audio_format: 'aac',
      sample_rate: 32000,
      provider: '',
    });

    const buf = new ArrayBuffer(8);
    ws.fireAudioChunk(buf);
    await nextTick();
    await nextTick();

    expect(mock.decodeAudioData).toHaveBeenCalled();
    expect(mock.createBuffer).not.toHaveBeenCalled();

    ws.restore();
  });
});

describe('useRealtimeVoice – decodeAudioData failure fallback', () => {
  beforeEach(() => {
    currentAudioFormat.value = 'opus';
    currentSampleRate.value = 24000;
    currentRealtimeProvider.value = '';
    installAudioContextMock();
    installMediaMock();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('decodeAudioData 失败时设置 errorMsg', async () => {
    const ws = buildFakeWebSocket();
    const mock = buildMockAudioContext();
    const decodeErr = new DOMException('Unable to decode audio data');
    mock.decodeAudioData.mockRejectedValue(decodeErr);
    mockAudioContext(mock.ctx);

    const { startCall, errorMsg } = useRealtimeVoice();
    await startCall();
    await nextTick();
    ws.fireControl({ type: 'ready' });
    ws.fireControl({
      type: 'assistant_sentence_start',
      audio_format: 'opus',
      sample_rate: 24000,
      provider: '',
    });

    // VAD may fail in jsdom; only check that the decode error is appended
    const prev = errorMsg.value;

    const buf = new ArrayBuffer(4);
    ws.fireAudioChunk(buf);
    await nextTick();
    await nextTick();

    expect(errorMsg.value).not.toBeNull();
    expect(errorMsg.value).toContain('音频解码失败');
    expect(mock.decodeAudioData).toHaveBeenCalled();

    ws.restore();
  });
});
