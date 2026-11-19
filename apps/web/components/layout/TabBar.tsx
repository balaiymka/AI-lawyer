"use client";

import { Calculator, FileText, House, MessageCircle, User } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { Dictionary, Locale } from "@/lib/i18n";

// Мобильная навигация, как нижний таб-бар в референсах. На десктопе скрыта.
export function TabBar({ locale, t }: { locale: Locale; t: Dictionary }) {
  const path = usePathname();
  if (path.includes("/admin")) return null; // в админке своё меню
  const items = [
    { icon: House, label: t.nav.home, href: `/${locale}`, active: path === `/${locale}` },
    { icon: MessageCircle, label: t.nav.chat, href: `/${locale}/chat`, active: path.startsWith(`/${locale}/chat`) },
    { icon: FileText, label: t.nav.documents, href: `/${locale}/documents`, active: path.startsWith(`/${locale}/documents`) },
    { icon: Calculator, label: t.nav.calculators, href: `/${locale}/calculators`, active: path.startsWith(`/${locale}/calculators`) },
    { icon: User, label: t.nav.profile, href: `/${locale}/profile`, active: path.startsWith(`/${locale}/profile`) },
  ];

  return (
    <nav
      aria-label="mobile"
      className="glass fixed inset-x-3 bottom-3 z-30 flex justify-between rounded-[26px] px-2 py-2 shadow-lg md:hidden"
    >
      {items.map(({ icon: Icon, label, active, href }) => (
        <Link
          key={label}
          href={href}
          aria-current={active ? "page" : undefined}
          className={`flex min-w-0 flex-1 flex-col items-center gap-1 rounded-2xl py-1.5 text-[10.5px] ${
            active ? "text-fg" : "text-muted"
          }`}
        >
          <span className={`grid size-8 place-items-center rounded-full ${active ? "bg-accent text-accent-fg" : ""}`}>
            <Icon className="size-[18px]" aria-hidden />
          </span>
          <span className="w-full truncate text-center">{label}</span>
        </Link>
      ))}
    </nav>
  );
}
