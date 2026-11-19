import Link from "next/link";

import { LogoMark } from "@/components/brand/Logo";
import { LangSwitch } from "@/components/layout/LangSwitch";
import { NavLinks } from "@/components/layout/NavLinks";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import type { Dictionary, Locale } from "@/lib/i18n";

export function Header({ locale, t }: { locale: Locale; t: Dictionary }) {
  const links = [
    { href: `/${locale}`, label: t.nav.home },
    { href: `/${locale}/chat`, label: t.nav.chat },
    { href: `/${locale}/documents`, label: t.nav.documents },
    { href: `/${locale}/calculators`, label: t.nav.calculators },
    { href: `/${locale}/library`, label: t.nav.library },
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/40 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 md:px-8">
        <Link href={`/${locale}`} className="flex items-center gap-2.5">
          <span className="text-fg">
            <LogoMark size={38} />
          </span>
          <span className="leading-tight">
            <span className="block font-[family-name:var(--font-unbounded)] text-[14px] font-semibold tracking-wide">{t.brand}</span>
            <span className="hidden text-[11px] text-muted sm:block">{t.brandSub}</span>
          </span>
        </Link>

        <nav className="ml-6 hidden items-center gap-1 rounded-full border border-line bg-surface p-1 backdrop-blur-xl lg:flex" aria-label="main">
          <NavLinks links={links} />
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <LangSwitch locale={locale} />
          <ThemeToggle labels={t.theme} />
          <Link
            href={`/${locale}/profile`}
            className="hidden rounded-full border border-line px-4 py-2 text-sm font-medium transition hover:bg-surface-2 sm:block"
          >
            {t.nav.login}
          </Link>
        </div>
      </div>
    </header>
  );
}
