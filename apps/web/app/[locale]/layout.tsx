import type { Metadata, Viewport } from "next";
import { Inter, Unbounded } from "next/font/google";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import "../globals.css";
import { Providers } from "@/app/providers";
import { Aurora } from "@/components/fx/Aurora";
import { Header } from "@/components/layout/Header";
import { TabBar } from "@/components/layout/TabBar";
import { getDictionary, isLocale, locales } from "@/lib/i18n";

// cyrillic-ext содержит казахские буквы ә ғ қ ң ө ұ ү һ і
const inter = Inter({ subsets: ["latin", "cyrillic", "cyrillic-ext"], variable: "--font-inter", display: "swap" });
// Заголовки концепта «ЖКХ AI ЮРИСТ»
const unbounded = Unbounded({ subsets: ["latin", "cyrillic", "cyrillic-ext"], weight: ["400", "600", "800"], variable: "--font-unbounded", display: "swap" });

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = getDictionary(locale);
  return { title: t.meta.title, description: t.meta.description };
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eef2fb" },
    { media: "(prefers-color-scheme: dark)", color: "#060a1d" },
  ],
};

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const t = getDictionary(locale);

  return (
    <html lang={locale} className={`${inter.variable} ${unbounded.variable}`} suppressHydrationWarning>
      <body className="font-sans">
        <Providers>
          <Aurora />
          <Header locale={locale} t={t} />
          <main className="mx-auto w-full max-w-6xl px-4 pb-28 pt-4 md:px-8 md:pb-16">{children}</main>
          <TabBar locale={locale} t={t} />
        </Providers>
      </body>
    </html>
  );
}
