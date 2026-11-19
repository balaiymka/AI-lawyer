import { notFound } from "next/navigation";

import { CasesList } from "@/components/profile/CasesList";
import { getDictionary, isLocale } from "@/lib/i18n";

export default async function ProfilePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const t = getDictionary(locale);
  return (
    <div className="mx-auto max-w-3xl space-y-6 pt-4">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t.profile.title}</h1>
      <CasesList t={t} locale={locale} />
    </div>
  );
}
