import { Notification } from 'electron';

const active = new Set<Notification>();
let activate: (() => void) | undefined;
export function setNotificationActivator(handler: () => void) { activate = handler; }

export async function showLocalNotification(title: unknown, body: unknown) {
  if (typeof title !== 'string' || typeof body !== 'string' || !body || title.length > 100 || body.length > 2000) {
    return { ok: false, message: '通知内容格式不正确。' };
  }
  if (!Notification.isSupported()) return { ok: false, message: '当前系统不支持桌面通知。' };
  const notice = new Notification({ title, body });
  if (active.size >= 20) active.values().next().value?.close();
  active.add(notice);
  notice.once('click', () => activate?.());
  return new Promise<{ ok: boolean; message: string }>(resolve => {
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      resolve({ ok, message: ok ? '系统已接收桌面通知。' : '桌面通知未能显示，请检查系统通知设置。' });
    };
    const timer = setTimeout(() => { notice.close(); finish(false); }, 10000);
    notice.once('show', () => finish(true));
    notice.once('failed', () => { active.delete(notice); finish(false); });
    notice.once('close', () => { active.delete(notice); finish(false); });
    try { notice.show(); } catch { active.delete(notice); finish(false); }
  });
}

export function closeNotifications() {
  for (const notice of active) notice.close();
  active.clear();
}
