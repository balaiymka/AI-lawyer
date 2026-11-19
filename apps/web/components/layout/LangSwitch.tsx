"use client";

import { clsx } from "clsx";
import { usePathname, useRouter } from "next/navigation";

import { locales, type Locale } from "@/lib/i18n";

const LABEL: Record<Locale, string> = { kk: "ҚАЗ", ru: "РУС" };

export function LangSwitch({ locale }: { locale: Locale }) {
  const pathname = usePathname();
  const router = useRouter();

  function switchTo(next: Locale) {
    if (next === locale) return;
    document.cookie = `locale=${next}; path=/; max-age=31536000; samesite=lax`;
    const rest = pathname.split("/").slice(2).join("/");
    router.push(`/${next}${rest ? `/${rest}` : ""}`);
  }

  return (
    <div role="group" aria-label="Тіл / Язык" className="flex rounded-full border border-line bg-surface p-0.5">
      {locales.map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => switchTo(l)}
          aria-pressed={l === locale}
          className={clsx(
            "rounded-full px-3 py-1.5 text-xs font-semibold tracking-wide transition",
            l === locale ? "bg-accent text-accent-fg" : "text-muted hover:text-fg",
          )}
        >
          {LABEL[l]}
        </button>
      ))}
    </div>
  );
}
