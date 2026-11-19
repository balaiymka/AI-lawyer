"use client";

import { ChevronRight, Gauge, History, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useStaff } from "@/components/admin/AdminShell";
import { JobWatcher } from "@/components/admin/JobWatcher";
import { adminFetch, AdminError, post, ruDate, type Job } from "@/lib/admin";

type ActRow = {
  code: string; title_ru: string; act_type: string; hierarchy_level: number; adilet_id: string | null; url: string | null;
  versions: number; history_from: string | null; current_from: string | null; chunks: number; busy: boolean;
};
type EvalSummary = {
  at: string; n: number; "recall@1": number; "recall@5": number; "recall@10": number; mrr: number; sec_per_query: number;
  by_act: Record<string, { n: number; "recall@10": number }>;
  misses: { id: string; q: string; gold: string[]; top: string[] }[];
};
type Stats = { answers: number; cases: number; flagged: number; reviewed: number; verdicts: Record<string, number>; accuracy: number | null };

const LEVEL = ["", "Конституция", "Кодекс", "Закон", "Постановление", "Приказ", "Иное", "Иное"];
const input = "w-full rounded-2xl border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-electric/60";

function AddAct({ onStarted }: { onStarted: (j: Job) => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ code: "", adilet_id: "", title_ru: "", title_kk: "", act_type: "ministry_order", hierarchy_level: 5 });
  const [error, setError] = useState<string | null>(null);
  if (!open)
    return (
      <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm hover:bg-surface-2">
        <Plus className="size-4" /> Добавить акт
      </button>
    );
  return (
    <form className="glass grid gap-3 rounded-[22px] p-4 sm:grid-cols-2" onSubmit={async (e) => {
      e.preventDefault();
      setError(null);
      try {
        onStarted(await post<Job>("/v1/admin/acts", { ...f, code: f.code.toUpperCase(), title_kk: f.title_kk || null }));
        setOpen(false);
      } catch (err) {
        setError(err instanceof AdminError ? err.message : "Не удалось");
      }
    }}>
      <div className="space-y-1"><label htmlFor="na-id" className="text-xs font-medium">Идентификатор Adilet</label>
        <input id="na-id" required placeholder="V2000020284" value={f.adilet_id} onChange={(e) => setF({ ...f, adilet_id: e.target.value.trim() })} className={input} /></div>
      <div className="space-y-1"><label htmlFor="na-code" className="text-xs font-medium">Код в системе</label>
        <input id="na-code" required placeholder="RULES_TARIFF" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} className={input} /></div>
      <div className="space-y-1 sm:col-span-2"><label htmlFor="na-ru" className="text-xs font-medium">Название (рус.)</label>
        <input id="na-ru" required value={f.title_ru} onChange={(e) => setF({ ...f, title_ru: e.target.value })} className={input} /></div>
      <div className="space-y-1 sm:col-span-2"><label htmlFor="na-kk" className="text-xs font-medium">Название (каз.)</label>
        <input id="na-kk" value={f.title_kk} onChange={(e) => setF({ ...f, title_kk: e.target.value })} className={input} /></div>
      <div className="space-y-1"><label htmlFor="na-type" className="text-xs font-medium">Вид акта</label>
        <select id="na-type" value={f.act_type} onChange={(e) => setF({ ...f, act_type: e.target.value })} className={input}>
          <option value="code">Кодекс</option><option value="law">Закон</option><option value="gov_decree">Постановление Правительства</option>
          <option value="ministry_order">Приказ министра (правила, методика)</option><option value="other">Иное</option>
        </select></div>
      <div className="space-y-1"><label htmlFor="na-lvl" className="text-xs font-medium">Уровень иерархии</label>
        <select id="na-lvl" value={f.hierarchy_level} onChange={(e) => setF({ ...f, hierarchy_level: Number(e.target.value) })} className={input}>
          {[1, 2, 3, 4, 5, 6].map((l) => <option key={l} value={l}>{l} — {LEVEL[l]}</option>)}
        </select></div>
      {error && <p className="text-sm text-danger sm:col-span-2">{error}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button type="submit" className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg">Скачать и проиндексировать</button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-full border border-line px-4 py-2 text-sm">Отмена</button>
      </div>
    </form>
  );
}

export function ActsPanel() {
  const user = useStaff();
  const { locale } = useParams<{ locale: string }>();
  const [acts, setActs] = useState<ActRow[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [quality, setQuality] = useState<EvalSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = user?.role === "admin";

  const load = useCallback(() => {
    adminFetch<ActRow[]>("/v1/admin/acts").then(setActs).catch((e) => setError(e.message));
    adminFetch<Stats>("/v1/admin/stats").then(setStats).catch(() => {});
    adminFetch<EvalSummary | null>("/v1/admin/eval/retrieval").then(setQuality).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const start = async (path: string) => {
    try {
      const r = await post<Job | Job[]>(path);
      setJobs((js) => [...(Array.isArray(r) ? r : [r]), ...js]);
      load();
    } catch (e) {
      setError(e instanceof AdminError ? e.message : "Не удалось");
    }
  };

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Законы и редакции</h1>
          <p className="text-sm text-muted">База знаний AI-юриста: акты, их редакции и состояние индекса поиска</p>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => start("/v1/admin/acts/check-updates")} className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg">
              <RefreshCw className="size-4" /> Проверить обновления всех актов
            </button>
          </div>
        )}
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[["Ответов AI", stats.answers], ["Проверено юристом", stats.reviewed], ["Помечено на проверку", stats.flagged],
            ["Точность по проверенным", stats.accuracy === null ? "—" : `${Math.round(stats.accuracy * 100)}%`]].map(([l, v]) => (
            <div key={String(l)} className="glass rounded-[20px] p-4">
              <p className="text-xs text-muted">{l}</p>
              <p className="mt-1 text-2xl font-semibold tabular">{v}</p>
            </div>
          ))}
        </div>
      )}

      <section className="glass rounded-[24px] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-2xl bg-electric/10 text-electric"><Gauge className="size-5" aria-hidden /></span>
            <div>
              <p className="text-sm font-semibold">Качество поиска норм</p>
              <p className="text-xs text-muted">
                {quality
                  ? `Контрольный набор: ${quality.n} вопросов · проверено ${ruDate(quality.at)} · ${quality.sec_per_query.toFixed(1)} с на вопрос`
                  : "Ещё не проверялось — запустите контрольный набор вопросов"}
              </p>
            </div>
          </div>
          {isAdmin && (
            <button type="button" onClick={() => start("/v1/admin/eval/retrieval")} className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm hover:bg-surface-2">
              <Gauge className="size-4" /> Проверить качество
            </button>
          )}
        </div>
        {quality && (
          <>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {([["Нужная норма первой", quality["recall@1"]], ["В первых 5", quality["recall@5"]], ["В первых 10", quality["recall@10"]]] as const).map(([l, v]) => (
                <div key={l} className="rounded-2xl bg-surface-2 p-3">
                  <p className="text-[11px] text-muted">{l}</p>
                  <p className="text-xl font-semibold tabular">{Math.round(v * 100)}%</p>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(quality.by_act).map(([a, v]) => (
                <span key={a} className="rounded-full border border-line px-2.5 py-1 text-[11px] tabular">{a}: {Math.round(v["recall@10"] * 100)}% · {v.n}</span>
              ))}
            </div>
            {quality.misses.length > 0 && (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-muted">Промахи: {quality.misses.length}</summary>
                <ul className="mt-2 space-y-1.5">
                  {quality.misses.map((m) => (
                    <li key={m.id} className="rounded-xl bg-surface-2 px-3 py-2">
                      <p>{m.q}</p>
                      <p className="text-muted">нужно: {m.gold.join(", ")} · найдено: {m.top.slice(0, 3).join(", ") || "—"}</p>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>

      {error && <p className="rounded-xl bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
      {jobs.length > 0 && <div className="grid gap-2 sm:grid-cols-2">{jobs.slice(0, 6).map((j) => <JobWatcher key={j.id} jobId={j.id} onFinish={load} />)}</div>}
      {isAdmin && <AddAct onStarted={(j) => setJobs((js) => [j, ...js])} />}

      <div className="glass overflow-x-auto rounded-[24px]">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-4 py-3 font-medium">Акт</th>
              <th className="px-4 py-3 font-medium">Уровень</th>
              <th className="px-4 py-3 font-medium">Действующая редакция</th>
              <th className="px-4 py-3 font-medium">Редакций в базе</th>
              <th className="px-4 py-3 text-right font-medium">Фрагментов</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {!acts && <tr><td colSpan={6} className="px-4 py-6"><div className="h-4 animate-pulse rounded bg-surface-2" /></td></tr>}
            {acts?.map((a) => (
              <tr key={a.code} className="border-b border-line/60 last:border-0">
                <td className="max-w-[360px] px-4 py-3">
                  <Link href={`/${locale}/admin/acts/${a.code}`} className="font-semibold hover:underline">{a.code}</Link>
                  <p className="truncate text-xs text-muted">{a.title_ru}</p>
                </td>
                <td className="px-4 py-3 text-xs text-muted">{a.hierarchy_level} · {LEVEL[a.hierarchy_level] ?? ""}</td>
                <td className="whitespace-nowrap px-4 py-3 tabular">с {ruDate(a.current_from)}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1.5 tabular">
                    {a.versions > 1 && <History className="size-3.5 text-electric" aria-label="есть история" />}
                    {a.versions}{a.versions > 1 && <span className="text-xs text-muted">с {ruDate(a.history_from)}</span>}
                  </span>
                </td>
                <td className="px-4 py-3 text-right tabular">{a.chunks.toLocaleString("ru-RU")}</td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    {a.busy && <span className="text-xs text-electric">задача идёт…</span>}
                    {isAdmin && !a.busy && (
                      <button type="button" onClick={() => start(`/v1/admin/acts/${a.code}/check-updates`)} title="Проверить обновления на Adilet"
                        aria-label={`Проверить обновления ${a.code}`} className="grid size-9 place-items-center rounded-full border border-line hover:bg-surface-2">
                        <RefreshCw className="size-4" />
                      </button>
                    )}
                    <Link href={`/${locale}/admin/acts/${a.code}`} aria-label={`Открыть ${a.code}`} className="grid size-9 place-items-center rounded-full hover:bg-surface-2">
                      <ChevronRight className="size-4" />
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
