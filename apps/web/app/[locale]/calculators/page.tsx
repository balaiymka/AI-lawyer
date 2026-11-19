import { notFound } from "next/navigation";
import { Suspense } from "react";

import { CalculatorTabs } from "@/components/calculators/CalculatorTabs";
import { getDictionary, isLocale } from "@/lib/i18n";

export default async function CalculatorsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const t = getDictionary(locale);
  return (
    <div className="space-y-6 pt-4">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t.calc.title}</h1>
        <p className="mt-2 text-muted">{t.calc.subtitle}</p>
      </header>
      <Suspense>
        <CalculatorTabs t={t} locale={locale} />
      </Suspense>
    </div>
  );
}
