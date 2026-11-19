"use client";

import { clsx } from "clsx";
import { ArrowLeft, ExternalLink, GitCompare, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useStaff } from "@/components/admin/AdminShell";
import { JobWatcher } from "@/components/admin/JobWatcher";
import { adminFetch, AdminError, del, post, ruDate, ruDateTime, type Job } from "@/lib/admin";

type Version = { id: string; valid_from: string; valid_to: string | null; is_current: boolean; units: number; fetched_at: string };
type Act = { code: string; title_ru: string; url: string | null; adilet_id: string | null; chunks: number };
type Compare = {
  from_version: { valid_from: string; valid_to: string | null }; to_version: { valid_from: string; valid_to: string | null };
  stats: Record<string, number>;
  new_articles: { path: string; title: string }[]; removed_articles: { path: string; title: string }[];
  changed_articles: { path: string; title: string; changed: number; added: number; removed: number }[];
};

const today = () => new Date().toISOString().slice(0, 10);
const input = "rounded-2xl border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-electric/60";

export function ActDetail({ code }: { code: string }) {
  const user = useStaff();
  const isAdmin = user?.role === "admin";
  const { locale } = useParams<{ locale: string }>();
  const [act, setAct] = useState<Act | null>(null);
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [jobs, setJobs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [on, setOn] = useState("2020-07-01");
  const [d1, setD1] = useState("");
  const [d2, setD2] = useState(today());
  const [cmp, setCmp] = useState<Compare | null>(null);
  const [cmpBusy, setCmpBusy] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const load = useCallback(() => {
    adminFetch<Act[]>("/v1/admin/acts").then((all) => setAct(all.find((a) => a.code === code) ?? null)).catch(() => {});
    adminFetch<Version[]>(`/v1/admin/acts/${code}/versions`)
      .then((v) => {
        setVersions(v);
        setD1((cur) => cur || v.at(-1)?.valid_from || today());
      })
      .catch((e) => setError(e.message));
  }, [code]);
  useEffect(load, [load]);

  const run = async (fn: () => Promise<Job>) => {
    setError(null);
    try {
      const j = await fn();
      setJobs((js) => [j.id, ...js]);
    } catch (e) {
      setError(e instanceof AdminError ? e.message : "Не удалось");
    }
  };

  const compare = async () => {
    setCmpBusy(true);
    setError(null);
    try {
      setCmp(await adminFetch<Compare>(`/v1/admin/acts/${code}/compare?d1=${d1}&d2=${d2}`));
    } catch (e) {
      setCmp(null);
      setError(e instanceof AdminError ? e.message : "Не удалось сравнить");
    } finally {
      setCmpBusy(false);
    }
  };

  const span = versions && versions.length ? { from: new Date(versions.at(-1)!.valid_from).getTime(), to: Date.now() } : null;

  return (
    <>
      <div>
        <Link href={`/${locale}/admin`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4" /> Все акты</Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{code}</h1>
        <p className="text-sm text-muted">{act?.title_ru}</p>
        {act?.url && (
          <a href={act.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-electric hover:underline">
            Adilet: {act.adilet_id} <ExternalLink className="size-3" />
          </a>
        )}
      </div>

      {error && <p className="rounded-xl bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
      {jobs.length > 0 && <div className="grid gap-2 sm:grid-cols-2">{jobs.map((id) => <JobWatcher key={id} jobId={id} onFinish={load} />)}</div>}

      <section className="glass space-y-4 rounded-[24px] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Редакции в базе</h2>
          {isAdmin && (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => run(() => post<Job>(`/v1/admin/acts/${code}/check-updates`))}
                className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg">
                <RefreshCw className="size-4" /> Проверить обновления
              </button>
              <button type="button" onClick={() => run(() => post<Job>(`/v1/admin/acts/${code}/reindex`))}
                className="rounded-full border border-line px-4 py-2 text-sm hover:bg-surface-2">Переиндексировать</button>
            </div>
          )}
        </div>

        {span && versions && (
          <div className="relative h-10 rounded-full bg-surface-2" aria-label="Шкала редакций">
            {versions.map((v) => {
              const a = new Date(v.valid_from).getTime();
              const b = v.valid_to ? new Date(v.valid_to).getTime() : Date.now();
              const left = ((a - span.from) / (span.to - span.from)) * 100;
              const width = Math.max(0.8, ((b - a) / (span.to - span.from)) * 100);
              return (
                <span key={v.id} title={`${ruDate(v.valid_from)} – ${v.valid_to ? ruDate(v.valid_to) : "сегодня"}`}
                  className={clsx("absolute top-2 h-6 rounded-full", v.is_current ? "bg-electric" : "bg-lavender/70")}
                  style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }} />
              );
            })}
            <span className="absolute -bottom-5 left-0 text-[10px] text-muted tabular">{ruDate(versions.at(-1)!.valid_from)}</span>
            <span className="absolute -bottom-5 right-0 text-[10px] text-muted">сегодня</span>
          </div>
        )}

        <div className="overflow-x-auto pt-3">
          <table className="w-full min-w-[560px] text-sm">
            <thead><tr className="border-b border-line text-left text-xs text-muted">
              <th className="py-2 pr-3 font-medium">Действовала</th><th className="py-2 pr-3 font-medium">Единиц</th>
              <th className="py-2 pr-3 font-medium">Загружена</th><th className="py-2" />
            </tr></thead>
            <tbody>
              {versions?.map((v) => (
                <tr key={v.id} className="border-b border-line/60 last:border-0">
                  <td className="py-2.5 pr-3 tabular">
                    {ruDate(v.valid_from)} – {v.valid_to ? ruDate(v.valid_to) : "сейчас"}
                    {v.is_current && <span className="ml-2 rounded-full bg-electric/15 px-2 py-0.5 text-[11px] font-semibold text-electric">действующая</span>}
                  </td>
                  <td className="py-2.5 pr-3 tabular">{v.units}</td>
                  <td className="py-2.5 pr-3 text-xs text-muted tabular">{ruDateTime(v.fetched_at)}</td>
                  <td className="py-2.5 text-right">
                    {isAdmin && !v.is_current && confirmId !== v.id && (
                      <button type="button" aria-label="Удалить редакцию" title="Удалить редакцию" onClick={() => setConfirmId(v.id)}
                        className="ml-auto grid size-8 place-items-center rounded-full text-muted hover:bg-danger/10 hover:text-danger">
                        <Trash2 className="size-4" />
                      </button>
                    )}
                    {confirmId === v.id && (
                      <span className="inline-flex items-center gap-2 text-xs">
                        Удалить редакцию безвозвратно?
                        <button type="button" onClick={() => { setConfirmId(null); void run(() => del<Job>(`/v1/admin/versions/${v.id}`)); }}
                          className="rounded-full bg-danger px-3 py-1 font-semibold text-white">Удалить</button>
                        <button type="button" onClick={() => setConfirmId(null)} className="rounded-full border border-line px-3 py-1">Отмена</button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {isAdmin && (
          <form className="flex flex-wrap items-end gap-2 border-t border-line pt-4" onSubmit={(e) => { e.preventDefault(); run(() => post<Job>(`/v1/admin/acts/${code}/editions`, { on })); }}>
            <div className="space-y-1">
              <label htmlFor="ed-on" className="text-xs font-medium">Загрузить редакцию, действовавшую на дату</label>
              <input id="ed-on" type="date" required value={on} max={today()} onChange={(e) => setOn(e.target.value)} className={input} />
            </div>
            <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm font-medium hover:bg-surface-2">Загрузить</button>
            <p className="w-full text-xs text-muted">Текст скачивается с Adilet на казахском и русском; векторы неизменившихся пунктов переиспользуются.</p>
          </form>
        )}
      </section>

      <section className="glass space-y-4 rounded-[24px] p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold"><GitCompare className="size-5 text-electric" /> Сравнение редакций</h2>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); void compare(); }}>
          <div className="space-y-1"><label htmlFor="c-d1" className="text-xs font-medium">На дату A</label>
            <input id="c-d1" type="date" required value={d1} onChange={(e) => setD1(e.target.value)} className={input} /></div>
          <div className="space-y-1"><label htmlFor="c-d2" className="text-xs font-medium">На дату B</label>
            <input id="c-d2" type="date" required value={d2} onChange={(e) => setD2(e.target.value)} className={input} /></div>
          <button type="submit" disabled={cmpBusy} className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-60">
            {cmpBusy ? "Сравниваем…" : "Сравнить"}
          </button>
        </form>
        {cmp && (
          <div className="space-y-4">
            <p className="text-sm text-muted">Редакция с {ruDate(cmp.from_version.valid_from)} → редакция с {ruDate(cmp.to_version.valid_from)}</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {[["Статей", `${cmp.stats.articles_before} → ${cmp.stats.articles_after}`], ["Пунктов", `${cmp.stats.points_before} → ${cmp.stats.points_after}`],
                ["Новых статей", cmp.stats.new_articles], ["Исключённых", cmp.stats.removed_articles], ["Изменённых", cmp.stats.changed_articles]].map(([l, v]) => (
                <div key={String(l)} className="rounded-2xl border border-line bg-surface-2 p-3">
                  <p className="text-[11px] text-muted">{l}</p><p className="text-lg font-semibold tabular">{v}</p>
                </div>
              ))}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div><h3 className="mb-2 text-sm font-semibold text-success">Новые статьи</h3>
                <ul className="max-h-72 space-y-1 overflow-auto text-sm">{cmp.new_articles.map((a) => <li key={a.path}>{a.title}</li>)}
                  {!cmp.new_articles.length && <li className="text-muted">нет</li>}</ul></div>
              <div><h3 className="mb-2 text-sm font-semibold text-danger">Исключённые статьи</h3>
                <ul className="max-h-72 space-y-1 overflow-auto text-sm">{cmp.removed_articles.map((a) => <li key={a.path}>{a.title}</li>)}
                  {!cmp.removed_articles.length && <li className="text-muted">нет</li>}</ul></div>
            </div>
            <div className="overflow-x-auto">
              <h3 className="mb-2 text-sm font-semibold">Статьи с наибольшими изменениями</h3>
              <table className="w-full min-w-[520px] text-sm"><thead><tr className="border-b border-line text-left text-xs text-muted">
                <th className="py-2 font-medium">Статья</th><th className="py-2 text-right font-medium">изменено</th>
                <th className="py-2 text-right font-medium">добавлено</th><th className="py-2 text-right font-medium">исключено</th></tr></thead>
                <tbody>{cmp.changed_articles.slice(0, 25).map((a) => (
                  <tr key={a.path} className="border-b border-line/60"><td className="py-2 pr-3">{a.title}</td>
                    <td className="py-2 text-right tabular">{a.changed}</td><td className="py-2 text-right tabular">{a.added}</td>
                    <td className="py-2 text-right tabular">{a.removed}</td></tr>))}</tbody></table>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
