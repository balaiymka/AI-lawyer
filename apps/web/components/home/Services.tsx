import { ArrowUpRight, BookOpen, FileSearch, History, MessageSquareText, ReceiptText, ShieldAlert } from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";

import { Spotlight } from "@/components/fx/Spotlight";
import type { Dictionary, Locale } from "@/lib/i18n";

// Шесть возможностей из концепта. То, чего ещё нет в продукте, помечено «скоро» и ведёт в чат.
export function Services({ t, locale }: { t: Dictionary; locale: Locale }) {
  const s = t.services;
  const items = [
    { icon: MessageSquareText, tint: "#6E95FF", text: s.consult, href: `/${locale}/chat` },
    { icon: ReceiptText, tint: "#FFB86B", text: s.bills, href: `/${locale}/chat`, soon: true },
    { icon: ShieldAlert, tint: "#B9A8FF", text: s.complaints, href: `/${locale}/documents/complaint_housing_inspection` },
    { icon: FileSearch, tint: "#6E95FF", text: s.analysis, href: `/${locale}/chat`, soon: true },
    { icon: BookOpen, tint: "#9FE3B8", text: s.rights, href: `/${locale}/library` },
    { icon: History, tint: "#DCE6FF", text: s.history, href: `/${locale}/profile` },
  ];
  return (
    <section aria-labelledby="services">
      <h2 id="services" className="mb-4 font-[family-name:var(--font-unbounded)] text-xl font-semibold tracking-tight">{s.title}</h2>
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {items.map(({ icon: Icon, tint, text: [title, desc], href, soon }, i) => (
          <li key={title} className="rise" style={{ "--i": i } as CSSProperties}>
            <Link href={href} className="block h-full">
              <Spotlight tint={tint} className="glass group flex h-full flex-col gap-3 rounded-[24px] p-4 transition duration-300 hover:-translate-y-1">
                <span className="flex items-start justify-between">
                  <span className="grid size-11 place-items-center rounded-2xl" style={{ background: `color-mix(in srgb, ${tint} 20%, transparent)`, color: tint }}>
                    <Icon className="size-5" aria-hidden />
                  </span>
                  {soon ? (
                    <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10.5px] font-semibold text-muted">{s.soon}</span>
                  ) : (
                    <ArrowUpRight className="size-4 text-muted transition group-hover:text-fg" aria-hidden />
                  )}
                </span>
                <span className="mt-2 text-[15px] font-bold leading-snug">{title}</span>
                <span className="text-[12.5px] leading-relaxed text-muted">{desc}</span>
              </Spotlight>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
