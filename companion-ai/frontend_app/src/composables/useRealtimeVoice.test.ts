import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
import {
  currentAudioFormat,
  currentRealtimeProvider,
  currentSampleRate,
  useRealtimeVoice,
} from './useRealtimeVoice';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function buildFakeWebSocket() {
  let instance: any = null;

  const origWS = globalThis.WebSocket;
  const MockWS = vi.fn(function (this: any, _url: string) {
    this.readyState = WebSocket.OPEN;
    this.binaryType = 'arraybuffer';
    this.url = '';
    this.send = vi.fn();
    this.close = vi.fn();
    this.onopen = null;
    this.onerror = null;
    this.onclose = null;
    this.onmessage = null;
    instance = this;
    // Fire onopen on next microtask so startCall() resolves
    queueMicrotask(() => {
      if (this.onopen) this.onopen({} as Event);
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
    vi.spyOn(globalThis, 'AudioContext' as any).mockReturnValue(mockAudioCtx.ctx);

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
    vi.spyOn(globalThis, 'AudioContext' as any).mockReturnValue(buildMockAudioContext().ctx);

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
    vi.spyOn(globalThis, 'AudioContext' as any).mockReturnValue(buildMockAudioContext().ctx);

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
    vi.spyOn(globalThis, 'AudioContext' as any).mockReturnValue(mock.ctx);

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
    vi.spyOn(globalThis, 'AudioContext' as any).mockReturnValue(mock.ctx);

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
    vi.spyOn(globalThis, 'AudioContext' as any).mockReturnValue(mock.ctx);

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
    vi.spyOn(globalThis, 'AudioContext' as any).mockReturnValue(mock.ctx);

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
    vi.spyOn(globalThis, 'AudioContext' as any).mockReturnValue(mock.ctx);

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
    expect(errorMsg.value).toContain('opus');

    ws.restore();
  });
});
