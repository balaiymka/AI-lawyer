"use client";

import { clsx } from "clsx";
import { Activity, BookCheck, Gavel, ListTodo, LogOut, Scale, Users } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { adminFetch, AdminError, getToken, post, setToken, type StaffUser } from "@/lib/admin";

const Ctx = createContext<StaffUser | null>(null);
export const useStaff = () => useContext(Ctx);

function Login({ onDone }: { onDone: (u: StaffUser) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="mx-auto mt-10 max-w-sm">
      <form
        className="glass space-y-4 rounded-[28px] p-6"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const r = await post<{ token: string; user: StaffUser }>("/v1/auth/login", { email, password });
            setToken(r.token);
            onDone(r.user);
          } catch (err) {
            setError(err instanceof AdminError ? err.message : "Сервер недоступен");
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="flex items-center gap-3">
          <span className="ai-orb size-9" aria-hidden />
          <div>
            <h1 className="text-xl font-semibold">Админка</h1>
            <p className="text-xs text-muted">Вход для администратора и юриста</p>
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="adm-email" className="text-sm font-medium">Email</label>
          <input id="adm-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-2xl border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-electric/60" />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="adm-pass" className="text-sm font-medium">Пароль</label>
          <input id="adm-pass" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-2xl border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-electric/60" />
        </div>
        {error && <p className="rounded-xl bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
        <button type="submit" disabled={busy} className="w-full rounded-full bg-accent py-2.5 text-sm font-semibold text-accent-fg disabled:opacity-60">
          {busy ? "Входим…" : "Войти"}
        </button>
      </form>
    </div>
  );
}

export function AdminShell({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<StaffUser | null>(null);
  const [checked, setChecked] = useState(false);
  const { locale } = useParams<{ locale: string }>();
  const path = usePathname();

  const check = useCallback(() => {
    if (!getToken()) {
      setUser(null);
      setChecked(true);
      return;
    }
    adminFetch<StaffUser>("/v1/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecked(true));
  }, []);

  useEffect(() => {
    check();
    const out = () => setUser(null);
    window.addEventListener("zhkh24-admin-logout", out);
    return () => window.removeEventListener("zhkh24-admin-logout", out);
  }, [check]);

  if (!checked) return <div className="glass mx-auto mt-10 h-40 max-w-sm animate-pulse rounded-[28px]" />;
  if (!user) return <Login onDone={setUser} />;

  const base = `/${locale}/admin`;
  const nav = [
    { href: base, label: "Законы", icon: Scale, exact: true },
    { href: `${base}/review`, label: "Проверка ответов", icon: BookCheck },
    { href: `${base}/jobs`, label: "Задачи", icon: ListTodo },
    { href: `${base}/status`, label: "Состояние системы", icon: Activity },
    ...(user.role === "admin" ? [{ href: `${base}/users`, label: "Сотрудники", icon: Users }] : []),
  ];

  return (
    <Ctx.Provider value={user}>
      <div className="flex flex-wrap gap-5 pt-2">
        <aside className="glass flex w-full flex-col gap-1 rounded-[24px] p-3 md:w-56 md:self-start">
          <p className="flex items-center gap-2 px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-muted">
            <Gavel className="size-3.5" aria-hidden /> Админка
          </p>
          <nav aria-label="Разделы админки" className="flex flex-wrap gap-1 md:flex-col">
            {nav.map(({ href, label, icon: Icon, exact }) => {
              const active = exact ? path === href : path.startsWith(href);
              return (
                <Link key={href} href={href} aria-current={active ? "page" : undefined}
                  className={clsx("flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition",
                    active ? "bg-accent font-semibold text-accent-fg" : "text-muted hover:bg-surface-2 hover:text-fg")}>
                  <Icon className="size-4" aria-hidden />
                  {label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-2 border-t border-line px-2 pt-3 text-xs text-muted">
            <p className="truncate font-medium text-fg">{user.full_name || user.email}</p>
            <p>{user.role === "admin" ? "администратор" : "юрист"}</p>
            <button type="button" onClick={() => { setToken(null); setUser(null); }}
              className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 hover:bg-surface-2">
              <LogOut className="size-3.5" aria-hidden /> Выйти
            </button>
          </div>
        </aside>
        <div className="min-w-0 flex-[999_1_560px] space-y-5">{children}</div>
      </div>
    </Ctx.Provider>
  );
}
