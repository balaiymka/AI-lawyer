"use client";

import { clsx } from "clsx";
import { AlertTriangle, BadgeCheck, CalendarClock } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { adminFetch, AdminError, post, ruDate, ruDateTime } from "@/lib/admin";

type Item = {
  id: string; created_at: string; question: string | null; event_date: string | null;
  verdict: string | null; verdict_text: string | null; summary: string | null; legal_answer: string | null;
  legal_basis: { act: string; article: string; point: string; quote: string; quote_verified: boolean }[];
  mode: string | null; verification: { removed_citations: string[]; replaced_quotes: number; unverified_refs: string[]; needs_review: boolean } | null;
  needs_review: boolean; model: string | null; review: { verdict: string; comment: string | null } | null;
};

const FILTERS = [["pending", "Не проверены"], ["flagged", "Помечены"], ["reviewed", "Проверены"], ["all", "Все"]] as const;
const VERDICTS = [
  ["correct", "Верно", "bg-success text-white"],
  ["wrong_norm", "Неверная норма", "bg-danger text-white"],
  ["outdated", "Устарело", "bg-warning text-black"],
  ["incomplete", "Неполно", "bg-electric text-white"],
] as const;
const AI_VERDICT: Record<string, string> = { yes: "Прав", no: "Не прав", partly: "Частично", depends: "Зависит" };

function Card({ item, onSaved }: { item: Item; onSaved: () => void }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async (verdict: string) => {
    setBusy(true);
    setError(null);
    try {
      await post(`/v1/admin/review/${item.id}`, { verdict, comment: comment || null });
      onSaved();
    } catch (e) {
      setError(e instanceof AdminError ? e.message : "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  };
  const v = item.verification;
  return (
    <article className="glass space-y-3 rounded-[22px] p-5">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="tabular">{ruDateTime(item.created_at)}</span>
        {item.mode && <span className="rounded-full bg-surface-2 px-2 py-0.5">{item.mode === "llm" ? "AI" : "демо"}</span>}
        {item.event_date && <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5"><CalendarClock className="size-3" /> событие {ruDate(item.event_date)}</span>}
        {item.needs_review && <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-warning"><AlertTriangle className="size-3" /> на проверку</span>}
        {item.review && <span className="rounded-full bg-success/15 px-2 py-0.5 font-semibold text-success">проверено: {VERDICTS.find((x) => x[0] === item.review!.verdict)?.[1]}</span>}
      </div>
      <p className="rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm text-accent-fg">{item.question ?? "—"}</p>
      {item.verdict_text && <p className="text-sm"><b>{AI_VERDICT[item.verdict ?? ""] ?? ""}:</b> {item.verdict_text}</p>}
      {item.summary && <p className="text-sm text-muted">{item.summary}</p>}
      {item.legal_answer && (
        <details className="rounded-2xl border border-line bg-surface p-3 text-sm"><summary className="cursor-pointer font-medium">Для юриста</summary>
          <p className="mt-2 whitespace-pre-line text-fg/90">{item.legal_answer}</p></details>
      )}
      {item.legal_basis.length > 0 && (
        <ul className="space-y-2">
          {item.legal_basis.map((b, i) => (
            <li key={i} className="rounded-2xl border border-line p-3 text-xs">
              <p className="flex items-center gap-1.5 font-semibold">
                {b.quote_verified ? <BadgeCheck className="size-3.5 text-success" /> : <AlertTriangle className="size-3.5 text-warning" />}
                {[b.article && `ст. ${b.article}`, b.point && `п. ${b.point}`].filter(Boolean).join(" ")} · <span className="font-normal text-muted">{b.act}</span>
              </p>
              <p className="mt-1 text-muted">{b.quote}</p>
            </li>
          ))}
        </ul>
      )}
      {v && (v.removed_citations.length > 0 || v.replaced_quotes > 0 || v.unverified_refs.length > 0) && (
        <p className="rounded-xl bg-warning/10 px-3 py-2 text-xs text-warning">
          Проверка ссылок: удалено {v.removed_citations.length}, заменено цитат {v.replaced_quotes}
          {v.unverified_refs.length > 0 && `, статьи вне найденного: ${v.unverified_refs.join(", ")}`}
        </p>
      )}
      <div className="space-y-2 border-t border-line pt-3">
        <label htmlFor={`c-${item.id}`} className="sr-only">Комментарий юриста</label>
        <textarea id={`c-${item.id}`} rows={2} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Комментарий: какая норма верная, что упущено…"
          className="w-full rounded-2xl border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-electric/60" />
        <div className="flex flex-wrap gap-2">
          {VERDICTS.map(([k, label, cls]) => (
            <button key={k} type="button" disabled={busy} onClick={() => save(k)} className={clsx("rounded-full px-3.5 py-1.5 text-xs font-semibold disabled:opacity-50", cls)}>{label}</button>
          ))}
        </div>
        {error && <p className="text-xs text-danger">{error}</p>}
      </div>
    </article>
  );
}

export function ReviewPanel() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("pending");
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setItems(null);
    adminFetch<Item[]>(`/v1/admin/review?status=${filter}`).then(setItems).catch((e) => setError(e.message));
  }, [filter]);
  useEffect(load, [load]);
  return (
    <>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Проверка ответов</h1>
        <p className="text-sm text-muted">Юрист оценивает ответы AI: из этих оценок считается точность и собирается тестовый набор</p>
      </div>
      <div role="tablist" className="glass inline-flex flex-wrap rounded-full p-1">
        {FILTERS.map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={filter === k} onClick={() => setFilter(k)}
            className={clsx("rounded-full px-4 py-1.5 text-sm transition", filter === k ? "bg-accent font-semibold text-accent-fg" : "text-muted hover:text-fg")}>{label}</button>
        ))}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      {!items && <div className="glass h-40 animate-pulse rounded-[22px]" />}
      {items && items.length === 0 && <p className="glass rounded-[22px] p-5 text-sm text-muted">Здесь пусто.</p>}
      <div className="space-y-4">{items?.map((it) => <Card key={it.id} item={it} onSaved={load} />)}</div>
    </>
  );
}
