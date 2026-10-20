import { computed, reactive } from 'vue';

export const ACCESS_API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, '') || 'http://127.0.0.1:8000';
const SESSION_KEY = 'companion_access_session';
let sessionToken = '';
try { sessionToken = sessionStorage.getItem(SESSION_KEY) || ''; } catch { /* optional storage */ }
export const accessState = reactive({ mode: 'local' as 'local' | 'key', authenticated: true,
  userId: null as string | null, role: 'admin' as string | null, error: '', privacyPending: false });
export const canManage = computed(() => accessState.role === 'admin');
export function currentUserId() { return accessState.userId || 'user_001'; }
export function userStorageKey(base: string) {
  return accessState.mode === 'key' && accessState.userId ? `${base}:${accessState.userId}` : base;
}
export function sessionProtocols(): string[] | undefined {
  return sessionToken ? ['companion.session', sessionToken] : undefined;
}
export function hasAccessSession() { return !!sessionToken; }
function clearSession() {
  sessionToken = '';
  accessState.authenticated = false;
  accessState.userId = accessState.role = null;
  accessState.privacyPending = false;
  try { sessionStorage.removeItem(SESSION_KEY); } catch { /* optional storage */ }
}
export function clearUserCachedData(userId: string, mode = accessState.mode) {
  for (const base of ['companion_chat_history', 'companion_session_id', 'companion_user_name']) {
    localStorage.removeItem(mode === 'key' ? `${base}:${userId}` : base);
  }
  for (const prefix of ['companion_push_since_v2_', 'companion_seen_reminders_']) localStorage.removeItem(prefix + userId);
}
async function reconcileUserData(data: { authenticated: boolean; user_id: string | null; mode: 'key' | 'local' }) {
  if (!data.authenticated) return;
  const user = data.user_id || 'user_001';
  const response = await apiFetch(`${ACCESS_API_BASE}/privacy/user/${encodeURIComponent(user)}/status`);
  if (!response.ok) throw new Error('无法核对数据清理状态，请重新连接。');
  const receipt = await response.json();
  accessState.privacyPending = receipt.status === 'pending';
  if (receipt.job_id) {
    const key = `companion_privacy_receipt:${user}`;
    if (localStorage.getItem(key) !== receipt.job_id) clearUserCachedData(user, data.mode);
    localStorage.setItem(key, receipt.job_id);
  }
}
export async function apiFetch(input: string, options: RequestInit = {}): Promise<Response> {
  const issuedToken = sessionToken;
  let firstParty = false;
  try { firstParty = new URL(input, ACCESS_API_BASE).origin === new URL(ACCESS_API_BASE).origin; } catch { /* invalid URL */ }
  let init = options;
  if (firstParty && sessionToken) {
    const headers = new Headers(options.headers);
    headers.set('Authorization', `Bearer ${sessionToken}`);
    init = { ...options, headers };
  }
  const response = await fetch(input, init);
  if (firstParty && issuedToken === sessionToken && response.status === 401 && !input.endsWith('/access/login') && !input.endsWith('/access/status')) {
    clearSession();
    accessState.error = '登录已失效，请重新登录。';
  }
  return response;
}
function applyStatus(data: { mode: 'local' | 'key'; authenticated: boolean; user_id: string | null; role: string | null }) {
  accessState.mode = data.mode;
  accessState.authenticated = data.authenticated;
  accessState.userId = data.user_id;
  accessState.role = data.role;
  if (!data.authenticated) clearSession();
}
export async function checkAccess() {
  const issuedToken = sessionToken;
  const response = await apiFetch(`${ACCESS_API_BASE}/access/status`);
  if (!response.ok) throw new Error('无法连接服务，请检查后端是否已启动。');
  const data = await response.json();
  if (issuedToken === sessionToken) { await reconcileUserData(data); if (issuedToken === sessionToken) applyStatus(data); }
}
export async function loginAccess(accessKey: string) {
  const response = await fetch(`${ACCESS_API_BASE}/access/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ access_key: accessKey }),
  });
  if (!response.ok) throw new Error(response.status === 429 ? '登录会话已满，请稍后重试。' : '访问密钥无效，或服务端访问配置不可用。');
  const data = await response.json();
  sessionToken = data.session_token;
  try { sessionStorage.setItem(SESSION_KEY, sessionToken); } catch { /* session-only memory fallback */ }
  await reconcileUserData(data);
  if (sessionToken !== data.session_token) return;
  applyStatus(data);
  accessState.error = '';
}
export async function logoutAccess() {
  const issuedToken = sessionToken;
  try { await apiFetch(`${ACCESS_API_BASE}/access/logout`, { method: 'POST' }); }
  catch { accessState.error = '已在本机退出，暂时无法通知服务器。'; }
  finally { if (issuedToken === sessionToken) clearSession(); }
}
