import { BadgeCheck, Building2, ClipboardList, Droplets, Hammer, MessageSquareText, Receipt, Scale, Volume2, Zap } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { CSSProperties } from "react";

import { Spotlight } from "@/components/fx/Spotlight";
import { AnswerPreview } from "@/components/home/AnswerPreview";
import { AskBox } from "@/components/home/AskBox";
import { Hero } from "@/components/home/Hero";
import { LawTicker } from "@/components/home/LawTicker";
import { QuorumDial } from "@/components/home/QuorumDial";
import { RouteTicket } from "@/components/home/RouteTicket";
import { Services } from "@/components/home/Services";
import { getDictionary, isLocale } from "@/lib/i18n";

const delay = (i: number) => ({ "--i": i }) as CSSProperties;

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const t = getDictionary(locale);

  const scenarios = [
    { icon: Droplets, label: t.scenarios.flood, tint: "#6E95FF" },
    { icon: ClipboardList, label: t.scenarios.osiReport, tint: "#FFB86B" },
    { icon: Receipt, label: t.scenarios.tariffs, tint: "#9FE3B8" },
    { icon: Volume2, label: t.scenarios.noise, tint: "#B9A8FF" },
    { icon: Hammer, label: t.scenarios.redevelopment, tint: "#FF8F86" },
    { icon: Building2, label: t.scenarios.developer, tint: "#FFCF6B" },
  ];
  const steps = [
    { icon: MessageSquareText, title: t.how.s1, text: t.how.s1t },
    { icon: Scale, title: t.how.s2, text: t.how.s2t },
    { icon: Zap, title: t.how.s3, text: t.how.s3t },
  ];

  return (
    <div className="space-y-12 md:space-y-16">
      <Hero t={t} locale={locale} />

      <section aria-labelledby="ask" className="grid items-center gap-6 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div>
          <h2 id="ask" className="font-[family-name:var(--font-unbounded)] text-2xl font-semibold tracking-tight sm:text-3xl">{t.hero.askTitle}</h2>
          <p className="mt-3 flex items-center gap-2 text-sm text-muted">
            <BadgeCheck className="size-4 text-success" aria-hidden />
            {t.trust}
          </p>
        </div>
        <AskBox t={t} />
      </section>

      <Services t={t} locale={locale} />

      <LawTicker t={t} locale={locale} />

      <section aria-labelledby="scenarios">
        <h2 id="scenarios" className="mb-4 font-[family-name:var(--font-unbounded)] text-xl font-semibold tracking-tight">{t.scenarios.title}</h2>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {scenarios.map(({ icon: Icon, label, tint }, i) => (
            <li key={label} className="rise" style={delay(i)}>
              <Link href={`/${locale}/chat?q=${encodeURIComponent(label)}`} className="block h-full">
                <Spotlight tint={tint} className="glass group flex h-full w-full flex-col items-start gap-8 rounded-[24px] p-4 text-left transition duration-300 hover:-translate-y-1">
                  <span className="grid size-11 place-items-center rounded-2xl transition duration-300 group-hover:-rotate-6 group-hover:scale-110"
                    style={{ background: `color-mix(in srgb, ${tint} 20%, transparent)`, color: tint }}>
                    <Icon className="size-5" aria-hidden />
                  </span>
                  <span className="text-sm font-medium leading-snug">{label}</span>
                </Spotlight>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.25fr_1fr]">
        <AnswerPreview t={t} locale={locale} />
        <RouteTicket t={t} locale={locale} />
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.25fr_1fr]">
        <div className="glass rounded-[28px] p-6 md:p-8">
          <h2 className="font-[family-name:var(--font-unbounded)] text-xl font-semibold tracking-tight">{t.how.title}</h2>
          <ol className="relative mt-6 space-y-7 before:absolute before:bottom-3 before:left-[21px] before:top-3 before:w-px before:bg-gradient-to-b before:from-electric before:to-lavender/30">
            {steps.map(({ icon: Icon, title, text }, i) => (
              <li key={title} className="relative flex gap-4">
                <span className="relative grid size-11 shrink-0 place-items-center rounded-full border border-line bg-surface-2">
                  <Icon className="size-5 text-electric" aria-hidden />
                </span>
                <div>
                  <p className="text-xs font-medium text-muted tabular">0{i + 1}</p>
                  <p className="text-lg font-semibold">{title}</p>
                  <p className="mt-0.5 text-sm text-muted">{text}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
        <QuorumDial t={t} href={`/${locale}/calculators`} />
      </section>

      <p className="mx-auto max-w-2xl text-center text-xs text-muted">{t.disclaimer}</p>
    </div>
  );
}
