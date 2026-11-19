import { BadgeCheck, FileText } from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";

import type { Dictionary } from "@/lib/i18n";

// Как будет выглядеть ответ AI-юриста: суть, норма, план, документ.
export function AnswerPreview({ t, locale }: { t: Dictionary; locale: string }) {
  const p = t.preview;
  const d = (i: number) => ({ "--i": i }) as CSSProperties;
  return (
    <article className="glass flex h-full flex-col gap-4 rounded-[28px] p-5 shadow-[var(--shadow)]">
      <div className="flex items-center justify-between">
        <h2 className="text-sm text-muted">{p.title}</h2>
        <span className="rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-medium">{p.badge}</span>
      </div>

      <p className="rise ml-auto max-w-[85%] rounded-[20px] rounded-br-md bg-accent px-4 py-3 text-sm text-accent-fg" style={d(1)}>
        {p.question}
      </p>

      <div className="rise flex gap-3" style={d(3)}>
        <span className="ai-orb mt-1 size-8 shrink-0" aria-hidden />
        <div className="min-w-0 flex-1 space-y-3 rounded-[20px] rounded-tl-md border border-line bg-surface-2 p-4">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-warm">{p.shortLabel}</p>
            <p className="mt-1 text-sm font-medium leading-relaxed">{p.short}</p>
            <span className="mt-2 inline-flex items-center gap-1 rounded-full border border-success/50 px-2 py-0.5 text-[11px] text-success">
              <BadgeCheck className="size-3.5" aria-hidden />
              {t.route.basis}
            </span>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-warm">{p.stepsLabel}</p>
            <ol className="mt-2 space-y-2">
              {p.steps.map((s, i) => (
                <li key={s} className="flex gap-2.5 text-sm leading-snug">
                  <span className="grid size-5 shrink-0 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold tabular">
                    {i + 1}
                  </span>
                  {s}
                </li>
              ))}
            </ol>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-dashed border-line p-3">
            <FileText className="size-5 text-warm" aria-hidden />
            <span className="flex-1 text-sm font-medium">{p.doc}</span>
            <Link href={`/${locale}/documents/protocol_copy_request`} className="rounded-full bg-accent px-3 py-1 text-xs font-semibold text-accent-fg transition hover:brightness-110">{p.docCta}</Link>
          </div>
        </div>
      </div>
    </article>
  );
}
