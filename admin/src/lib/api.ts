/**
 * 管理端 API 封装
 *
 * 登录用的是同一套 /api/v1/auth/login，但令牌单独存一个 key：
 * 这样在同一个浏览器里，管理端和用户端不会互相把对方挤下线。
 */
import type { UserDetail, UserPage } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

const TOKEN_KEY = "chef_admin_token";
const NAME_KEY = "chef_admin_name";

export function getAdminToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getAdminName(): string {
  return localStorage.getItem(NAME_KEY) || "";
}

export function setAdminAuth(token: string, username: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(NAME_KEY, username);
}

export function clearAdminAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(NAME_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (init.auth !== false) {
    const token = getAdminToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method: init.method ?? "GET",
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });

  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* 用默认文案 */
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

/* ---------------- 登录 ---------------- */

export function adminLogin(username: string, password: string) {
  return request<{ token: string; username: string }>("/api/v1/auth/login", {
    method: "POST",
    body: { username, password },
    auth: false,
  });
}

/* ---------------- 用户管理 ---------------- */

export function fetchUsers(params: { q?: string; page: number; size: number }) {
  const search = new URLSearchParams({
    page: String(params.page),
    size: String(params.size),
  });
  if (params.q) search.set("q", params.q);
  return request<UserPage>(`/api/v1/admin/users?${search.toString()}`);
}

export function fetchUser(userId: number) {
  return request<UserDetail>(`/api/v1/admin/users/${userId}`);
}

export function patchUser(
  userId: number,
  body: { is_admin?: boolean; weekly_token_quota?: number | null },
) {
  return request<UserDetail>(`/api/v1/admin/users/${userId}`, {
    method: "PATCH",
    body,
  });
}

export function logoutAllSessions(userId: number) {
  return request<{ removed_sessions: number }>(
    `/api/v1/admin/users/${userId}/logout-all`,
    { method: "POST" },
  );
}

export function resetUserPassword(userId: number) {
  return request<{ username: string; password: string }>(
    `/api/v1/admin/users/${userId}/reset-password`,
    { method: "POST" },
  );
}

export function deleteUser(userId: number) {
  return request<{ deleted: { user_id: number; username: string; threads: number } }>(
    `/api/v1/admin/users/${userId}`,
    { method: "DELETE" },
  );
}
