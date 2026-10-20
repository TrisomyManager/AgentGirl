import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useChat } from './useChat';
import { accessState } from './accessSession';

const api = vi.hoisted(() => ({ streamTurn: vi.fn() }));
vi.mock('./useApi', async () => {
  const { ref } = await import('vue');
  return {
    absoluteApiUrl: (url: string) => url,
    useApi: () => {
      const error = ref<string | null>(null);
      return { isLoading: ref(false), error, serverAvailable: ref(true), streamTurn: api.streamTurn,
        transcribeVoice: vi.fn(), clearError: () => { error.value = null; }, checkServer: vi.fn() };
    },
  };
});

beforeEach(() => {
  Object.assign(accessState, { mode: 'local', authenticated: true, userId: null, role: 'admin' });
  vi.resetAllMocks();
  const storage = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  });
});

describe('quiet acknowledgement in chat', () => {
  it('keeps each account history and session separate, and stops late stream callbacks after clearing', async () => {
    Object.assign(accessState, { mode: 'key', userId: 'alice', role: 'user' });
    const alice = useChat();
    api.streamTurn.mockResolvedValueOnce({ assistant_message: 'alice reply' });
    await alice.sendMessage('alice private message', { requestVoiceReply: false });
    const aliceSession = alice.sessionId.value;
    expect(api.streamTurn.mock.calls[0][0].user.user_id).toBe('alice');
    Object.assign(accessState, { userId: 'bob' });
    const bob = useChat();
    expect(bob.messages.value).toHaveLength(0);
    expect(bob.sessionId.value).not.toBe(aliceSession);
    api.streamTurn.mockResolvedValueOnce({ assistant_message: 'bob reply' });
    await bob.sendMessage('bob message', { requestVoiceReply: false });
    expect(api.streamTurn.mock.calls[1][0].user.user_id).toBe('bob');
    expect(localStorage.getItem('companion_chat_history:bob')).not.toContain('alice private');
    expect(localStorage.getItem('companion_chat_history:alice')).toContain('alice private');
    let finish!: (value: unknown) => void;
    let handlers: any;
    api.streamTurn.mockImplementationOnce(async (_request, callbacks) => {
      handlers = callbacks; return new Promise(resolve => { finish = resolve; });
    });
    const pending = bob.sendMessage('unfinished', { requestVoiceReply: false });
    bob.clearHistory();
    handlers.onMeta({ emotion: { primary: 'angry' } }); handlers.onToken('late private content');
    finish({ assistant_message: 'late private content' }); await pending;
    expect(bob.messages.value).toHaveLength(0);
    expect(bob.currentEmotion.value).toBe('neutral');
    expect(localStorage.getItem('companion_chat_history:bob')).toBeNull();
  });
  it('sends image-only input, retains the receipt but never stores original pixels in history', async () => {
    const images = ['data:image/png;base64,cGl4ZWxz'];
    api.streamTurn.mockResolvedValueOnce({ assistant_message: '一张图片' });
    const chat = useChat();
    await chat.sendMessage('', { imageUrls: images, requestVoiceReply: false });
    expect(api.streamTurn.mock.calls[0][0]).toMatchObject({ has_image: true, image_urls: images });
    expect(chat.messages.value[0]).toMatchObject({ imageUrls: images, imageCount: 1 });
    expect(localStorage.getItem('companion_chat_history')).not.toContain(images[0]);
    expect(useChat().messages.value[0].imageUrls).toBeUndefined();
    expect(useChat().messages.value[0].imageCount).toBe(1);
  });
  it('plays voice segments and keeps replay metadata without reporting a missing full URL', async () => {
    const segment = { turn_id: 't', seq: 0, text: '第一句', audio_url: '/first.mp3', duration_ms: 500 };
    api.streamTurn.mockImplementationOnce(async (_request, handlers) => {
      expect(_request.supports_segmented_voice).toBe(true);
      handlers.onVoiceSegment(segment);
      handlers.onVoiceDone({ segments: 1, successful_segments: 1 });
      return { assistant_message: '第一句', voice_mode: 'segmented', voice_url: null, voice_segments: [segment] };
    });
    const chat = useChat();
    chat.voice.playAudio = vi.fn(async () => {});
    await chat.sendMessage('讲两句', { requestVoiceReply: true });
    expect(chat.voice.playAudio).toHaveBeenCalledWith('/first.mp3', { avatarTimeline: undefined });
    expect(chat.messages.value.slice(-1)[0]?.voiceSynthesisError).toBeUndefined();
    expect(chat.messages.value.slice(-1)[0]?.voiceSegments).toEqual([segment]);
    expect(useChat().messages.value.slice(-1)[0]?.voiceSegments).toEqual([segment]);
  });
  it('keeps an interrupted task distinguishable from a completed tool', async () => {
    api.streamTurn.mockImplementationOnce(async (_request, handlers) => {
      handlers.onToolStatus({ tool_name: 'set_reminder', status: 'pending' });
      return { assistant_message: '请核对实际执行状态', task: { status: 'interrupted', message: '执行结果未确认' } };
    });
    const chat = useChat();
    await chat.sendMessage('先看时间再提醒我', { requestVoiceReply: false });
    expect(chat.toolStatus.currentTool.value?.status).toBe('error');
    expect(chat.toolStatus.currentTool.value?.message).toBe('执行结果未确认');
  });
  it('persists a user receipt without an empty assistant bubble, voice failure or loading state', async () => {
    api.streamTurn.mockImplementationOnce(async (_request, handlers) => {
      handlers.onMeta({ reply_suppressed: true });
      return { reply_suppressed: true, assistant_message: '', emotion: { primary: 'calm' } };
    });
    const chat = useChat();
    await chat.sendMessage('嗯', { requestVoiceReply: false });
    expect(chat.messages.value).toHaveLength(1);
    expect(chat.messages.value[0]).toMatchObject({ role: 'user', content: '嗯', quietlyAcknowledged: true });
    expect(chat.isTyping.value).toBe(false);
    expect(chat.error.value).toBeNull();
    expect(useChat().messages.value[0].quietlyAcknowledged).toBe(true);
    api.streamTurn.mockImplementationOnce(async (_request, handlers) => {
      handlers.onToken('我在听');
      return { assistant_message: '我在听', reply_suppressed: false };
    });
    await chat.sendMessage('我想说说今天的事', { requestVoiceReply: false });
    expect(chat.messages.value.slice(-1)[0]?.content).toBe('我在听');
    expect(chat.messages.value.slice(-1)[0]?.isTyping).toBe(false);
  });

  it('keeps a broken stream distinguishable from a successful quiet turn', async () => {
    api.streamTurn.mockImplementationOnce(async (_request, handlers) => {
      handlers.onMeta({ reply_suppressed: true });
      return null;
    });
    const chat = useChat();
    await chat.sendMessage('好的', { requestVoiceReply: false });
    expect(chat.messages.value[0].quietlyAcknowledged).toBeUndefined();
    expect(chat.messages.value.slice(-1)[0]?.content).toContain('连接中断');
  });

  it('remembers when automatic voice was disabled so refresh does not defeat the saved pacing preference', () => {
    const chat = useChat();
    expect(chat.voice.autoPlayEnabled.value).toBe(true);
    chat.voice.toggleAutoPlay();
    expect(useChat().voice.autoPlayEnabled.value).toBe(false);
  });
});
