import { notFound } from "next/navigation";

import { TemplateGallery } from "@/components/documents/TemplateGallery";
import { getDictionary, isLocale } from "@/lib/i18n";

export default async function DocumentsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const t = getDictionary(locale);
  return (
    <div className="space-y-8 pt-4">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t.docs.title}</h1>
        <p className="mt-2 max-w-2xl text-muted">{t.docs.subtitle}</p>
      </header>
      <TemplateGallery t={t} locale={locale} />
    </div>
  );
}
