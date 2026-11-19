import { notFound } from "next/navigation";

import { DocumentBuilder } from "@/components/documents/DocumentBuilder";
import { getDictionary, isLocale } from "@/lib/i18n";

export default async function DocumentPage({ params }: { params: Promise<{ locale: string; code: string }> }) {
  const { locale, code } = await params;
  if (!isLocale(locale) || !/^[a-z_]+$/.test(code)) notFound();
  return <DocumentBuilder code={code} t={getDictionary(locale)} locale={locale} />;
}
