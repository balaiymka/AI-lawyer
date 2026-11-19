import { API_URL } from "@/lib/chat";

// Токен сотрудника хранится в браузере; при 401 — выход на экран входа.
const KEY = "zhkh24-admin-token";

export type StaffUser = { id: string; email: string; full_name: string | null; role: "admin" | "lawyer" };

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {}
}

export class AdminError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function adminFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let msg = `Ошибка ${res.status}`;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join("; ") : msg;
    } catch {}
    if (res.status === 401) {
      setToken(null);
      window.dispatchEvent(new Event("zhkh24-admin-logout"));
    }
    throw new AdminError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const post = <T,>(path: string, body?: unknown) =>
  adminFetch<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const del = <T,>(path: string) => adminFetch<T>(path, { method: "DELETE" });

export type Job = {
  id: string; kind: string; title: string; act_code: string | null; created_by: string | null;
  status: "queued" | "running" | "done" | "failed"; log: string[]; result: unknown; error: string | null;
  created_at: string; finished_at: string | null;
};

export const ruDate = (iso: string | null | undefined) => (iso ? iso.slice(0, 10).split("-").reverse().join(".") : "—");
export const ruDateTime = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
