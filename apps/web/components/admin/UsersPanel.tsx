"use client";

import { Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useStaff } from "@/components/admin/AdminShell";
import { adminFetch, AdminError, del, post } from "@/lib/admin";

type Row = { id: string; email: string; full_name: string | null; role: "admin" | "lawyer" };
const input = "w-full rounded-2xl border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-electric/60";

export function UsersPanel() {
  const me = useStaff();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [f, setF] = useState({ email: "", full_name: "", role: "lawyer", password: "" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const load = useCallback(() => { adminFetch<Row[]>("/v1/admin/users").then(setRows).catch((e) => setMsg({ ok: false, text: e.message })); }, []);
  useEffect(load, [load]);

  if (me?.role !== "admin") return <p className="glass rounded-[22px] p-5 text-sm text-muted">Раздел доступен только администратору.</p>;
  return (
    <>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Сотрудники</h1>
        <p className="text-sm text-muted">Администратор управляет базой законов, юрист проверяет ответы AI</p>
      </div>
      <div className="glass overflow-x-auto rounded-[24px]">
        <table className="w-full min-w-[520px] text-sm">
          <thead><tr className="border-b border-line text-left text-xs text-muted">
            <th className="px-4 py-3 font-medium">Сотрудник</th><th className="px-4 py-3 font-medium">Роль</th><th className="px-4 py-3" /></tr></thead>
          <tbody>
            {rows?.map((r) => (
              <tr key={r.id} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-3"><p className="font-medium">{r.full_name || "—"}</p><p className="text-xs text-muted">{r.email}</p></td>
                <td className="px-4 py-3">{r.role === "admin" ? "администратор" : "юрист"}</td>
                <td className="px-4 py-3 text-right">
                  {r.id !== me.id && confirmId !== r.id && (
                    <button type="button" aria-label={`Удалить ${r.email}`} onClick={() => setConfirmId(r.id)}
                      className="ml-auto grid size-8 place-items-center rounded-full text-muted hover:bg-danger/10 hover:text-danger"><Trash2 className="size-4" /></button>
                  )}
                  {confirmId === r.id && (
                    <span className="inline-flex items-center gap-2 text-xs">Закрыть доступ?
                      <button type="button" onClick={async () => { setConfirmId(null); await del(`/v1/admin/users/${r.id}`); load(); }}
                        className="rounded-full bg-danger px-3 py-1 font-semibold text-white">Да</button>
                      <button type="button" onClick={() => setConfirmId(null)} className="rounded-full border border-line px-3 py-1">Нет</button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="glass grid gap-3 rounded-[22px] p-5 sm:grid-cols-2" onSubmit={async (e) => {
        e.preventDefault();
        setMsg(null);
        try {
          await post("/v1/admin/users", { ...f, full_name: f.full_name || null });
          setMsg({ ok: true, text: `Сотрудник ${f.email} добавлен. Передайте ему пароль лично.` });
          setF({ email: "", full_name: "", role: "lawyer", password: "" });
          load();
        } catch (err) {
          setMsg({ ok: false, text: err instanceof AdminError ? err.message : "Не удалось" });
        }
      }}>
        <h2 className="font-semibold sm:col-span-2">Добавить сотрудника</h2>
        <div className="space-y-1"><label htmlFor="u-email" className="text-xs font-medium">Email</label>
          <input id="u-email" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} className={input} /></div>
        <div className="space-y-1"><label htmlFor="u-name" className="text-xs font-medium">Имя</label>
          <input id="u-name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} className={input} /></div>
        <div className="space-y-1"><label htmlFor="u-role" className="text-xs font-medium">Роль</label>
          <select id="u-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} className={input}>
            <option value="lawyer">Юрист — проверка ответов</option><option value="admin">Администратор — база законов и сотрудники</option></select></div>
        <div className="space-y-1"><label htmlFor="u-pass" className="text-xs font-medium">Временный пароль (от 8 символов)</label>
          <input id="u-pass" type="password" autoComplete="new-password" required minLength={8} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} className={input} /></div>
        {msg && <p className={`text-sm sm:col-span-2 ${msg.ok ? "text-success" : "text-danger"}`}>{msg.text}</p>}
        <div className="sm:col-span-2"><button type="submit" className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg">Добавить</button></div>
      </form>
    </>
  );
}
