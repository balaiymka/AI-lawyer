import { ArrowRight, BadgeCheck, Send } from "lucide-react";

import Link from "next/link";

import type { Dictionary } from "@/lib/i18n";

// «Маршрут дела» — посадочный талон: Собственник ─✈─ ОСИ, вырезы на линии отрыва.
const BARS = [3, 1, 2, 1, 3, 2, 1, 1, 3, 1, 2, 2, 1, 3, 1, 2, 1, 1, 2, 3, 1, 2, 1, 3, 2, 1, 1, 2, 3, 1];

export function RouteTicket({ t, locale }: { t: Dictionary; locale: string }) {
  const r = t.route;
  return (
    <article
      className="ticket flex h-full flex-col rounded-[28px] bg-surface-2 shadow-[var(--shadow)]"
      style={{ ["--cut" as string]: "calc(100% - 96px)" }}
    >
      <div className="flex-1 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm text-muted">{r.title}</h2>
          <span className="flex items-center gap-1 rounded-full border border-success/60 px-2.5 py-1 text-[11px] font-medium text-success">
            <BadgeCheck className="size-3.5" aria-hidden />
            {r.verified}
          </span>
        </div>

        <div className="mt-6 flex items-center gap-3">
          <div className="min-w-0">
            <p className="truncate text-2xl font-semibold tracking-tight">{r.from}</p>
            <p className="truncate text-xs text-muted">{r.fromCaption}</p>
          </div>
          <div className="relative flex flex-1 items-center" aria-hidden>
            <span className="size-1.5 rounded-full bg-muted/60" />
            <span className="h-px flex-1 border-t border-dashed border-muted/50" />
            <span className="mx-1 whitespace-nowrap rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] font-medium tabular">
              {r.duration}
            </span>
            <span className="h-px flex-1 border-t border-dashed border-muted/50" />
            <Send className="ml-1 size-3.5 text-warm" />
          </div>
          <div className="min-w-0 text-right">
            <p className="truncate text-2xl font-semibold tracking-tight">{r.to}</p>
            <p className="truncate text-xs text-muted">{r.toCaption}</p>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-[1fr_auto] gap-4 rounded-2xl bg-surface p-4">
          <div>
            <p className="font-medium">{r.subject}</p>
            <p className="mt-1 text-xs text-muted">{r.basis}</p>
          </div>
          <p className="self-center text-right text-3xl font-semibold tabular text-warm">5</p>
        </div>
      </div>

      <div className="flex h-[96px] items-center gap-4 border-t-2 border-dashed border-line px-5">
        <div className="hidden h-10 items-stretch gap-[2px] opacity-60 sm:flex" aria-hidden>
          {BARS.map((w, i) => (
            <span key={i} className="bg-fg" style={{ width: w }} />
          ))}
        </div>
        <Link
          href={`/${locale}/documents/protocol_copy_request`}
          className="flex flex-1 items-center justify-center gap-2 rounded-full bg-accent py-3 text-sm font-semibold text-accent-fg transition hover:brightness-110"
        >
          {r.cta}
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      </div>
    </article>
  );
}
