"use client";

import { clsx } from "clsx";
import { ChevronRight, ExternalLink, MessageCircle, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiGet, fmtDate } from "@/lib/api";
import type { Dictionary, Locale } from "@/lib/i18n";

type TocItem = { type: "section" | "chapter" | "paragraph" | "article"; number: string | null; path: string; heading_ru: string | null; heading_kk: string | null; is_repealed: boolean };
type Toc = { act: string; title_ru: string; title_kk: string | null; url_ru: string | null; url_kk: string | null; valid_from: string; items: TocItem[] };
type Unit = { path: string; type: string; number: string | null; text_ru: string | null; text_kk: string | null };
type ActRow = { code: string; title_ru: string; title_kk: string | null; hierarchy_level: number };
type Article = { kind?: "chapter"; number: string; heading_ru: string | null; heading_kk: string | null; notes_ru: string | null; notes_kk: string | null; is_repealed: boolean; valid_from: string; text_ru?: string | null; text_kk?: string | null; units: Unit[] };

export function LawReader({ t, locale }: { t: Dictionary; locale: Locale }) {
  const l = t.lib;
  const params = useSearchParams();
  const router = useRouter();
  const current = params.get("a");
  const act = params.get("act") || "ZHO";
  const [acts, setActs] = useState<ActRow[]>([]);
  const [toc, setToc] = useState<Toc | null>(null);
  const [article, setArticle] = useState<Article | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState(false);
  const activeRef = useRef<HTMLAnchorElement>(null);
  const kk = locale === "kk";
  const head = (x: { heading_ru: string | null; heading_kk: string | null }) => (kk ? x.heading_kk || x.heading_ru : x.heading_ru || x.heading_kk) ?? "";

  useEffect(() => {
    apiGet<ActRow[]>("/v1/library/acts").then(setActs).catch(() => setError(true));
  }, []);

  useEffect(() => {
    setToc(null);
    apiGet<Toc>(`/v1/library/acts/${act}/toc`).then(setToc).catch(() => setError(true));
  }, [act]);

  useEffect(() => {
    if (!current) return setArticle(null);
    setArticle(null);
    apiGet<Article>(`/v1/library/acts/${act}/articles/${encodeURIComponent(current)}`).then(setArticle).catch(() => setError(true));
  }, [act, current]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [toc, current]);

  const hasArticles = !!toc?.items.some((i) => i.type === "article");
  const filtered = useMemo(() => {
    if (!toc) return [];
    const s = q.trim().toLowerCase();
    if (!s) return toc.items;
    return toc.items.filter((i) => (i.type === "article" || !hasArticles) && (i.number === s || i.number?.startsWith(s) || head(i).toLowerCase().includes(s)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toc, q, kk, hasArticles]);

  if (error && !toc) return <p className="glass rounded-[24px] p-5 text-sm text-danger">{l.apiError}</p>;
  const title = toc ? (kk ? toc.title_kk || toc.title_ru : toc.title_ru) : "…";
  const url = toc ? (kk ? toc.url_kk || toc.url_ru : toc.url_ru) : null;
  const open = (n: string) => router.replace(`/${locale}/library?act=${act}&a=${encodeURIComponent(n)}`, { scroll: false });
  const pickAct = (code: string) => router.replace(`/${locale}/library?act=${code}`, { scroll: false });

  return (
    <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className={clsx("glass flex flex-col rounded-[28px] lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)]", current && "hidden lg:flex")}>
        <div className="border-b border-line p-4">
          <label htmlFor="act-pick" className="sr-only">{l.toc}</label>
          <select id="act-pick" value={act} onChange={(e) => pickAct(e.target.value)}
            className="w-full rounded-2xl border border-line bg-surface-2 px-3 py-2 text-sm font-semibold outline-none focus:border-electric/60">
            {(acts.length ? acts : [{ code: act, title_ru: title, title_kk: title, hierarchy_level: 0 }]).map((a) => (
              <option key={a.code} value={a.code}>{kk ? a.title_kk || a.title_ru : a.title_ru}</option>
            ))}
          </select>
          <div className="relative mt-3">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={l.search} aria-label={l.search}
              className="w-full rounded-full border border-line bg-surface-2 py-2 pl-9 pr-3 text-sm outline-none focus:border-warm/60" />
          </div>
        </div>
        <nav aria-label={l.toc} className="min-h-0 flex-1 overflow-y-auto p-2">
          {!toc && Array.from({ length: 10 }).map((_, i) => <div key={i} className="m-2 h-4 animate-pulse rounded bg-surface-2" />)}
          {filtered.map((i) =>
            i.type === "article" || (!hasArticles && i.type === "chapter") ? (
              <a key={i.path} ref={(i.type === "chapter" ? i.path : i.number) === current ? activeRef : undefined}
                href={`?act=${act}&a=${i.type === "chapter" ? i.path : i.number}`}
                onClick={(e) => { e.preventDefault(); open(i.type === "chapter" ? i.path : i.number!); }}
                className={clsx("flex gap-2 rounded-xl px-3 py-1.5 text-[13px] leading-snug transition",
                  (i.type === "chapter" ? i.path : i.number) === current ? "bg-accent text-accent-fg" : "hover:bg-surface-2", i.is_repealed && "opacity-50")}>
                <span className="w-10 shrink-0 font-semibold tabular">{i.number}</span>
                <span className="min-w-0">{head(i) || (i.is_repealed ? l.repealed : "")}</span>
              </a>
            ) : (
              <p key={i.path} className={clsx("px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider text-warm", i.type === "paragraph" && "normal-case tracking-normal")}>
                {head(i) || (i.type === "section" ? (kk ? `${i.number}-бөлім` : `Раздел ${i.number}`) : i.number)}
              </p>
            ),
          )}
        </nav>
      </aside>

      <section className={clsx("min-w-0", !current && "hidden lg:block")}>
        {!current ? (
          <div className="glass grid min-h-64 place-items-center rounded-[28px] p-8 text-muted">{l.pick}</div>
        ) : !article ? (
          <div className="glass space-y-3 rounded-[28px] p-8">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-4 animate-pulse rounded bg-surface-2" />)}</div>
        ) : (
          <article className="glass rounded-[28px] p-6 sm:p-8">
            <button type="button" onClick={() => router.replace(`/${locale}/library`)} className="mb-4 text-sm text-muted lg:hidden">← {l.toc}</button>
            <p className="text-xs text-muted">{l.edition} {fmtDate(article.valid_from)}</p>
            <h2 className="mt-1 text-xl font-semibold leading-snug sm:text-2xl">
              {article.kind === "chapter"
                ? `${kk ? `${article.number.replace(/^.*ch/, "")}-тарау` : `Глава ${article.number.replace(/^.*ch/, "")}`}. ${head(article)}`
                : `${kk ? `${article.number}-${l.article.toLowerCase()}` : `${l.article} ${article.number}`}. ${head(article)}`}
            </h2>
            {article.is_repealed && <p className="mt-2 inline-flex rounded-full bg-danger/10 px-2.5 py-1 text-xs text-danger">{l.repealed}</p>}
            <div className="mt-5 space-y-3 text-[15px] leading-relaxed">
              {/* статья без пунктов хранит текст в самой статье (например, ст. 38 ЗЖО) */}
              {article.units.length === 0 && (kk ? article.text_kk || article.text_ru : article.text_ru || article.text_kk) && (
                <p className="whitespace-pre-line">{kk ? article.text_kk || article.text_ru : article.text_ru || article.text_kk}</p>
              )}
              {article.units.map((u) => {
                const text = (kk ? u.text_kk || u.text_ru : u.text_ru || u.text_kk) ?? "";
                return <p key={u.path} id={u.path} className="whitespace-pre-line">{text}</p>;
              })}
            </div>
            {(kk ? article.notes_kk : article.notes_ru) && (
              <p className="mt-5 border-t border-line pt-3 text-xs text-muted">{kk ? article.notes_kk : article.notes_ru}</p>
            )}
            <div className="mt-6 flex flex-wrap gap-2">
              <Link href={`/${locale}/chat?q=${encodeURIComponent(`${kk ? `${article.number}-бап` : `Статья ${article.number}`} ${head(article)} — ${kk ? "түсіндіріп беріңіз" : "объясните простыми словами"}`)}`}
                className="flex items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-accent-fg">
                <MessageCircle className="size-4" />
                {l.ask}
              </Link>
              {url && (
                <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-full border border-line px-4 py-2.5 text-sm hover:bg-surface-2">
                  {l.openAdilet}
                  <ExternalLink className="size-4" />
                </a>
              )}
            </div>
            <nav className="mt-6 flex justify-between border-t border-line pt-4 text-sm">
              {(() => {
                const arts = (toc?.items.filter((i) => i.type === (hasArticles ? "article" : "chapter")) ?? [])
                  .map((a) => ({ ...a, number: hasArticles ? a.number : a.path }));
                const idx = arts.findIndex((a) => a.number === current);
                const prev = arts[idx - 1];
                const next = arts[idx + 1];
                return (
                  <>
                    <span>{prev && <button type="button" onClick={() => open(prev.number!)} className="text-muted hover:text-fg">← {prev.number}</button>}</span>
                    <span>{next && <button type="button" onClick={() => open(next.number!)} className="flex items-center gap-1 text-muted hover:text-fg">{next.number}<ChevronRight className="size-4" /></button>}</span>
                  </>
                );
              })()}
            </nav>
          </article>
        )}
      </section>
    </div>
  );
}
