import { afterEach, beforeEach, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules(); sessionStorage.clear();
  const values = new Map<string, string>();
  vi.stubGlobal('localStorage', { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
});
afterEach(() => { vi.unstubAllGlobals(); });
const account = (name: string, token: string) => ({ mode: 'key', authenticated: true, user_id: name, role: 'user', session_token: token });

it('keeps only the session credential, binds storage and WebSocket identity, and never sends it to third parties', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json(account('alice', 'session-a')))
    .mockResolvedValue(Response.json({}));
  vi.stubGlobal('fetch', fetcher);
  const access = await import('./accessSession');
  await access.loginAccess('original-host-access-key');
  expect(sessionStorage.getItem('companion_access_session')).toBe('session-a');
  expect(JSON.stringify(sessionStorage)).not.toContain('original-host-access-key');
  expect(access.currentUserId()).toBe('alice');
  expect(access.userStorageKey('history')).toBe('history:alice');
  expect(access.sessionProtocols()).toEqual(['companion.session', 'session-a']);
  await access.apiFetch(`${access.ACCESS_API_BASE}/memory/user/alice/list`);
  expect(new Headers(fetcher.mock.calls.find(call => call[0].includes('/memory/'))![1].headers).get('Authorization')).toBe('Bearer session-a');
  await access.apiFetch('https://media.example/voice.mp3');
  expect(new Headers(fetcher.mock.calls.find(call => call[0].startsWith('https://media.example'))![1].headers).has('Authorization')).toBe(false);
  await access.logoutAccess();
  expect(access.accessState.authenticated).toBe(false);
  expect(access.sessionProtocols()).toBeUndefined();
  expect(sessionStorage.getItem('companion_access_session')).toBeNull();
});

it('clears revoked stored sessions, and a late old 401 cannot sign out the next account', async () => {
  sessionStorage.setItem('companion_access_session', 'expired');
  let finish!: (response: Response) => void;
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ mode: 'key', authenticated: false, user_id: null, role: null })).mockImplementation(async () => Response.json({ status: 'none' }));
  vi.stubGlobal('fetch', fetcher);
  const access = await import('./accessSession');
  await access.checkAccess();
  expect(access.hasAccessSession()).toBe(false);
  fetcher.mockResolvedValueOnce(Response.json(account('alice', 'session-a')));
  await access.loginAccess('alice-key');
  fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = access.apiFetch(`${access.ACCESS_API_BASE}/old-request`);
  fetcher.mockResolvedValueOnce(Response.json(account('bob', 'session-b')));
  await access.loginAccess('bob-key');
  finish(new Response('', { status: 401 })); await pending;
  expect(access.currentUserId()).toBe('bob');
  expect(access.accessState.authenticated).toBe(true);
  fetcher.mockResolvedValueOnce(new Response('', { status: 401 }));
  await access.apiFetch(`${access.ACCESS_API_BASE}/current-request`);
  expect(access.accessState.authenticated).toBe(false);
});

it('discards local credentials even when logout cannot reach the service', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(account('alice', 'session-a')))
    .mockResolvedValueOnce(Response.json({ status: 'none' })).mockRejectedValue(new Error('offline')));
  const access = await import('./accessSession');
  await access.loginAccess('alice-key'); await access.logoutAccess();
  expect(access.accessState.authenticated).toBe(false);
  expect(access.accessState.error).toContain('暂时无法通知服务器');
});

it('checks durable erasure receipts before showing an account and clears stale caches after a lost response', async () => {
  localStorage.setItem('companion_chat_history:alice', 'old private content');
  localStorage.setItem('companion_chat_history:bob', 'bob content');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(account('alice', 'session-a')))
    .mockResolvedValueOnce(Response.json({ status: 'completed', job_id: 'new-erasure-receipt' })));
  const access = await import('./accessSession');
  await access.loginAccess('alice-key');
  expect(localStorage.getItem('companion_chat_history:alice')).toBeNull();
  expect(localStorage.getItem('companion_chat_history:bob')).toBe('bob content');
  expect(localStorage.getItem('companion_privacy_receipt:alice')).toBe('new-erasure-receipt');
});
