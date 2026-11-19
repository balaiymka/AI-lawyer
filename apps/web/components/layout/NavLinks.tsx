"use client";

import { clsx } from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavLinks({ links }: { links: { href: string; label: string }[] }) {
  const path = usePathname();
  return (
    <>
      {links.map((l, i) => {
        const active = i === 0 ? path === l.href : path.startsWith(l.href);
        return (
          <Link key={l.href} href={l.href} aria-current={active ? "page" : undefined}
            className={clsx("rounded-full px-3.5 py-2 text-sm transition hover:bg-surface-2 hover:text-fg", active ? "bg-accent font-semibold text-accent-fg" : "text-muted")}>
            {l.label}
          </Link>
        );
      })}
    </>
  );
}
