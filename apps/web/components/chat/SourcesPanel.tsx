"use client";

import { clsx } from "clsx";
import { BookOpen, ExternalLink } from "lucide-react";
import { useEffect, useRef } from "react";

import type { Source } from "@/lib/chat";
import type { Dictionary } from "@/lib/i18n";

// «art42/p8» или «ZHO:art42/p8» → «ст. 42 п. 8»
function xrefLabel(path: string): string {
  const p = path.includes(":") ? path.split(":")[1] : path;
  const art = /art([\d-]+)/.exec(p)?.[1];
  const pt = /\/p([\d-]+)/.exec(p)?.[1];
  return [art && `ст. ${art}`, pt && `п. ${pt}`].filter(Boolean).join(" ") || p;
}

// Панель источников: все пункты закона, которые получила модель. Процитированные — подсвечены.
export function SourcesPanel({
  sources,
  cited,
  focused,
  t,
}: {
  sources: Source[];
  cited: Set<string>;
  focused: string | null;
  t: Dictionary["chat"];
}) {
  const refs = useRef(new Map<string, HTMLLIElement>());
  useEffect(() => {
    if (focused) refs.current.get(focused)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [focused]);

  return (
    <aside className="glass flex max-h-[calc(100dvh-7rem)] flex-col rounded-[28px]">
      <h2 className="flex items-center gap-2 border-b border-line px-5 py-4 text-sm font-medium">
        <BookOpen className="size-4 text-warm" aria-hidden />
        {t.sources}
        {sources.length > 0 && <span className="ml-auto rounded-full bg-surface-2 px-2 py-0.5 text-xs tabular">{sources.length}</span>}
      </h2>
      {sources.length === 0 ? (
        <p className="p-5 text-sm text-muted">{t.sourcesEmpty}</p>
      ) : (
        <ul className="space-y-2 overflow-y-auto p-3">
          {sources.map((s) => (
            <li
              key={s.chunk_id}
              ref={(el) => {
                if (el) refs.current.set(s.chunk_id, el);
              }}
              className={clsx(
                "rounded-2xl border p-3 text-sm transition",
                focused === s.chunk_id ? "border-warm bg-warm/10" : cited.has(s.chunk_id) ? "border-success/40 bg-surface-2" : "border-line opacity-80",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold tabular">
                  {[s.article && `ст. ${s.article}`, s.point && `п. ${s.point}`].filter(Boolean).join(" ")}
                </p>
                {s.url && (
                  <a href={s.url} target="_blank" rel="noreferrer" aria-label={t.openAdilet} className="text-muted hover:text-fg">
                    <ExternalLink className="size-3.5" />
                  </a>
                )}
              </div>
              <p className="mt-0.5 truncate text-[11px] text-muted">{s.act_title}</p>
              {s.xref_from && (
                <p className="mt-1 inline-flex rounded-full bg-accent/10 px-2 py-0.5 text-[10.5px] font-medium text-accent">
                  {t.xrefFrom} {xrefLabel(s.xref_from)}
                </p>
              )}
              {s.is_current === false && s.version_date && (
                <p className="mt-1 inline-flex rounded-full bg-warm/15 px-2 py-0.5 text-[10.5px] font-medium text-warm tabular">
                  {s.version_date.split("-").reverse().join(".")} – {s.valid_to ? s.valid_to.split("-").reverse().join(".") : "…"}
                </p>
              )}
              <p className="mt-2 line-clamp-5 text-xs leading-relaxed text-fg/80">{s.text}</p>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
