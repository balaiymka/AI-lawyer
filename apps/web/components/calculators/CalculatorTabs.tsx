"use client";

import { clsx } from "clsx";
import { Percent, Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";

import { PenaltyCalculator } from "@/components/calculators/PenaltyCalculator";
import { QuorumCalculator } from "@/components/calculators/QuorumCalculator";
import type { Dictionary, Locale } from "@/lib/i18n";

export function CalculatorTabs({ t, locale }: { t: Dictionary; locale: Locale }) {
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") === "penalty" ? "penalty" : "quorum";
  const tabs = [
    { id: "quorum", icon: Users, label: t.calc.tabs.quorum },
    { id: "penalty", icon: Percent, label: t.calc.tabs.penalty },
  ] as const;
  return (
    <div className="space-y-5">
      <div role="tablist" className="glass inline-flex rounded-full p-1">
        {tabs.map(({ id, icon: Icon, label }) => (
          <button key={id} role="tab" aria-selected={tab === id} type="button"
            onClick={() => router.replace(`/${locale}/calculators?tab=${id}`, { scroll: false })}
            className={clsx("flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition",
              tab === id ? "bg-accent text-accent-fg" : "text-muted hover:text-fg")}>
            <Icon className="size-4" />
            {label}
          </button>
        ))}
      </div>
      {tab === "quorum" ? <QuorumCalculator t={t} /> : <PenaltyCalculator t={t} locale={locale} />}
    </div>
  );
}
