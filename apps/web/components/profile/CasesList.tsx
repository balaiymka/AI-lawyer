"use client";

import { ArrowRight, Info, MessageCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { apiGet, fmtDate } from "@/lib/api";
import type { Dictionary, Locale } from "@/lib/i18n";

type CaseRow = { id: string; title: string | null; category: string | null; updated_at: string; turns: number };

export function CasesList({ t, locale }: { t: Dictionary; locale: Locale }) {
  const p = t.profile;
  const [rows, setRows] = useState<CaseRow[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    apiGet<CaseRow[]>("/v1/cases").then(setRows).catch(() => setError(true));
  }, []);

  return (
    <div className="space-y-5">
      <p className="flex gap-2 rounded-2xl border border-line bg-surface p-4 text-sm text-muted">
        <Info className="mt-0.5 size-4 shrink-0 text-warm" />
        {p.loginSoon}
      </p>
      <section className="glass rounded-[28px] p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{p.cases}</h2>
        {error && <p className="mt-3 text-sm text-danger">{t.chat.error}</p>}
        {rows && rows.length === 0 && (
          <div className="mt-4 space-y-4">
            <p className="text-sm text-muted">{p.empty}</p>
            <Link href={`/${locale}/chat`} className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-accent-fg">
              <MessageCircle className="size-4" />
              {p.ask}
            </Link>
          </div>
        )}
        <ul className="mt-4 divide-y divide-line">
          {!rows && !error && Array.from({ length: 3 }).map((_, i) => <li key={i} className="h-14 animate-pulse" />)}
          {rows?.map((r) => (
            <li key={r.id}>
              <Link href={`/${locale}/chat?case=${r.id}`} className="group flex items-center gap-4 py-3.5">
                <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent-soft"><MessageCircle className="size-4" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{r.title}</span>
                  <span className="block text-xs text-muted tabular">
                    {fmtDate(r.updated_at, true)} · {r.turns} {p.turns}
                  </span>
                </span>
                <ArrowRight className="size-4 text-muted transition group-hover:translate-x-1 group-hover:text-fg" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
