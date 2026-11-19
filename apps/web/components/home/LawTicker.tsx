import { BookOpenCheck } from "lucide-react";
import Link from "next/link";

import type { Dictionary } from "@/lib/i18n";

// «ст. 34-1 п. 9 — …» / «34-1-бап 9-тармақ — …» → «34-1»
const articleOf = (s: string) => s.match(/(?:ст\. )?(\d+(?:-\d+)?)/)?.[1] ?? "";

// Бегущая строка проверенных норм ЗРК «О жилищных отношениях».
export function LawTicker({ t, locale }: { t: Dictionary; locale: string }) {
  const items = [...t.ticker.items, ...t.ticker.items]; // дубль для бесшовной прокрутки
  return (
    <section aria-label={t.ticker.label} className="marquee -mx-4 overflow-hidden md:-mx-8">
      <ul className="marquee-track gap-3 py-1">
        {items.map((it, i) => (
          <li key={i} aria-hidden={i >= t.ticker.items.length} className="shrink-0">
            <Link
              href={`/${locale}/library?a=${articleOf(it)}`}
              tabIndex={i >= t.ticker.items.length ? -1 : undefined}
              className="glass flex items-center gap-2 rounded-full px-4 py-2 text-[13px] transition hover:border-warm/50"
            >
              <BookOpenCheck className="size-4 text-warm" aria-hidden />
              <span className="font-medium tabular">{it.split(" — ")[0]}</span>
              <span className="text-muted">{it.split(" — ")[1]}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
