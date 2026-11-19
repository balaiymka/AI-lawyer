"use client";

import { ArrowRight, ClipboardList, Droplets, FileText, Gavel, Landmark, ScrollText, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import type { TemplateDef } from "@/components/documents/types";
import { Spotlight } from "@/components/fx/Spotlight";
import { apiGet, refLabel } from "@/lib/api";
import type { Dictionary, Locale } from "@/lib/i18n";

const ICONS: Record<string, typeof FileText> = {
  protocol_copy_request: ScrollText,
  osi_report_request: ClipboardList,
  flood_act: Droplets,
  claim_neighbor: FileText,
  complaint_housing_inspection: ShieldAlert,
  lawsuit_damage: Gavel,
};
const TINT: Record<string, string> = { osi: "#f0a35e", flood: "#5aa9f0" };

export function TemplateGallery({ t, locale }: { t: Dictionary; locale: Locale }) {
  const [items, setItems] = useState<TemplateDef[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    apiGet<TemplateDef[]>(`/v1/documents/templates?lang=${locale}`).then(setItems).catch(() => setError(true));
  }, [locale]);

  if (error) return <p className="glass rounded-[24px] p-5 text-sm text-danger">{t.docs.apiError}</p>;
  if (!items)
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="glass h-44 animate-pulse rounded-[24px]" />
        ))}
      </div>
    );

  const groups = (["osi", "flood"] as const).map((c) => ({ c, list: items.filter((i) => i.category === c) }));
  return (
    <div className="space-y-8">
      {groups.map(({ c, list }) => (
        <section key={c}>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-medium text-muted">
            {c === "osi" ? <Landmark className="size-4" /> : <Droplets className="size-4" />}
            {t.docs.categories[c]}
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((tpl, i) => {
              const Icon = ICONS[tpl.code] ?? FileText;
              return (
                <li key={tpl.code} className="rise" style={{ ["--i" as string]: i }}>
                  <Link href={`/${locale}/documents/${tpl.code}`} className="block h-full">
                    <Spotlight tint={TINT[c]} className="glass group flex h-full flex-col rounded-[24px] p-5 transition duration-300 hover:-translate-y-1">
                      <span className="grid size-11 place-items-center rounded-2xl" style={{ background: `color-mix(in srgb, ${TINT[c]} 18%, transparent)`, color: TINT[c] }}>
                        <Icon className="size-5" aria-hidden />
                      </span>
                      <p className="mt-5 font-semibold">{tpl.title}</p>
                      <p className="mt-1 flex-1 text-sm text-muted">{tpl.description}</p>
                      <div className="mt-4 flex items-center justify-between gap-2">
                        <span className="flex flex-wrap gap-1">
                          {tpl.basis.slice(0, 2).map((b) => (
                            <span key={b} className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-muted tabular">{refLabel(b, locale)}</span>
                          ))}
                        </span>
                        <span className="flex items-center gap-1 text-sm font-medium text-warm transition group-hover:gap-2">
                          {t.docs.open}
                          <ArrowRight className="size-4" />
                        </span>
                      </div>
                    </Spotlight>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
