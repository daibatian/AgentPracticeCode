/** 管理端用到的几个格式化函数 */

/** token 数量：10 万以下带千分位，10 万~99 万一位小数，100 万以上取整 */
export function formatTokens(value: number): string {
  if (value >= 10000) {
    const wan = value / 10000;
    return `${wan >= 100 ? Math.round(wan) : wan.toFixed(1)} 万`;
  }
  return value.toLocaleString("zh-CN");
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** 2026-09-15 18:30 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** 2026-09-15 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** 9 月 21 日 0 点 */
export function formatResetTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "下周一 0 点";
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日 0 点`;
}

/** 刚刚 / 5 分钟前 / 3 小时前 / 昨天 / 09-11 */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "—";

  const diff = Date.now() - time;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diff < minute) return "刚刚";
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  if (diff < 2 * day) return "昨天";
  return formatDate(iso);
}
