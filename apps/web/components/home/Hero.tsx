import { ArrowUpRight, BadgeCheck, FileText } from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";

import { Building } from "@/components/home/Building";
import type { Dictionary, Locale } from "@/lib/i18n";

const d = (i: number) => ({ "--i": i }) as CSSProperties;

// Hero в стиле концепта: полночная сцена в белой скруглённой рамке, огромный заголовок, дом поверх него.
export function Hero({ t, locale }: { t: Dictionary; locale: Locale }) {
  const h = t.hero;
  return (
    <section className="rounded-[44px] bg-surface-2 p-2 shadow-[var(--shadow)] sm:p-3">
      <div className="hero-stage relative overflow-hidden rounded-[36px] px-5 pb-6 pt-6 sm:px-8 sm:pb-8">
        <div aria-hidden className="pointer-events-none absolute -left-24 top-1/3 size-[460px] rounded-full bg-[#7C5CFF] opacity-25 blur-[110px]" />
        <div aria-hidden className="pointer-events-none absolute -right-20 -top-20 size-[420px] rounded-full bg-[#2F6BFF] opacity-35 blur-[120px]" />
        <div aria-hidden className="pointer-events-none absolute bottom-10 right-1/4 size-60 rounded-full bg-[#FFB86B] opacity-15 blur-[90px]" />

        <h1 className="rise relative z-[1] m-0 text-[clamp(52px,11vw,164px)] font-extrabold leading-[0.92] tracking-[-0.035em]" style={d(0)}>
          {h.h1a} <span className="text-gradient font-normal">{h.h1b}</span>
          <span className="-mt-[0.08em] block text-right">{h.h1c}</span>
        </h1>

        <div className="relative flex flex-wrap items-center justify-between gap-6 md:-mt-[clamp(80px,15vw,250px)]">
          <div className="rise relative z-[3] flex max-w-[340px] flex-[1_1_260px] flex-col gap-5 md:pt-[clamp(0px,11vw,170px)]" style={d(2)}>
            <p className="m-0 text-xl leading-snug text-[#DCE6FF]">{h.subtitle}</p>
            <p className="m-0 text-sm leading-relaxed text-[#9FB4E8]">{h.lead}</p>
            <Link href={`/${locale}/chat`} className="glow-btn inline-flex items-center gap-3 self-start rounded-full bg-[#F5F7FF] py-2 pl-6 pr-2 text-[15px] font-bold text-[#0B1640] transition hover:brightness-105">
              {h.cta}
              <span className="grid size-10 place-items-center rounded-full bg-[#2F6BFF] text-white"><ArrowUpRight className="size-[18px]" /></span>
            </Link>
          </div>

          <div className="relative z-[2] mx-auto w-full max-w-[460px] flex-[1_1_300px]">
            <Building className="block h-auto w-full" />
          </div>

          <div className="rise glass-dark relative z-[3] max-w-[300px] flex-[1_1_260px] rounded-[26px] p-4 md:mt-[clamp(120px,13vw,210px)] shadow-[0_30px_60px_-30px_rgba(0,0,0,0.6)]" style={d(4)}>
            <div className="flex items-center gap-2.5">
              <span className="ai-orb size-8" aria-hidden />
              <span className="flex flex-col leading-tight">
                <span className="text-[13px] font-bold">{h.previewName}</span>
                <span className="text-[11px] text-[#9FE3B8]">{h.previewStatus}</span>
              </span>
            </div>
            <p className="mb-0 mt-3 rounded-[16px] rounded-br-[4px] bg-[#F5F7FF]/90 px-3 py-2.5 text-[12.5px] leading-snug text-[#0B1640]">{h.previewQ}</p>
            <p className="mb-0 mt-2.5 text-[12.5px] leading-relaxed text-[#E8EEFF]">{h.previewA}</p>
            <span className="mt-2.5 inline-flex items-center gap-1.5 rounded-full border border-[#9FE3B8]/50 px-2.5 py-1 text-[11px] font-semibold text-[#9FE3B8]">
              <BadgeCheck className="size-3.5" aria-hidden />
              {h.previewBasis}
            </span>
          </div>
        </div>

        <div className="relative z-[3] mt-2 flex flex-wrap items-center justify-between gap-4 md:-mt-6">
          <div className="flex flex-wrap gap-2">
            {["Қазақша", "Русский", "Шала-қазақша"].map((l) => (
              <span key={l} className="rounded-full border border-white/15 bg-white/[0.07] px-3.5 py-2 text-xs text-[#DCE6FF]">{l}</span>
            ))}
          </div>
          <Link href={`/${locale}/documents/protocol_copy_request`} className="flex items-center gap-3 rounded-[22px] border border-[#B9A8FF]/35 bg-[#0B1640]/55 py-2.5 pl-2.5 pr-4 backdrop-blur-xl transition hover:border-[#B9A8FF]/70">
            <span className="grid size-11 place-items-center rounded-2xl bg-[#FFB86B]/15 text-[#FFB86B]"><FileText className="size-5" aria-hidden /></span>
            <span className="flex flex-col leading-tight">
              <span className="text-[13px] font-bold">{h.docCard}</span>
              <span className="text-[11px] text-[#B9C8F2]">{h.docCardSub}</span>
            </span>
          </Link>
        </div>
      </div>
    </section>
  );
}
