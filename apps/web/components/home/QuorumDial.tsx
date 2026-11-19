"use client";

import { ArrowRight, Minus, Plus } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import type { Dictionary } from "@/lib/i18n";

// Интерактивный циферблат кворума (по мотивам термостата из референса smart home).
// Правило — ст. 42 п. 8 ЗЖО: собрание правомочно, если участвует более половины собственников.
const R = 74;
const C = 2 * Math.PI * R;
const ARC = 0.75; // 270°

function polar(angleDeg: number, radius: number) {
  const a = ((angleDeg - 90) * Math.PI) / 180;
  return { x: 100 + radius * Math.cos(a), y: 100 + radius * Math.sin(a) };
}

const fill = (s: string, v: Record<string, number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k]));

export function QuorumDial({ t, href }: { t: Dictionary; href: string }) {
  const q = t.quorum;
  const id = useId();
  const [total, setTotal] = useState(100);
  const [n, setN] = useState(58);
  const count = Math.min(n, total);
  const share = total ? count / total : 0;
  const ok = count > total / 2;
  const need = Math.floor(total / 2) + 1 - count;
  const color = ok ? "var(--success)" : "var(--warm)";
  const end = polar(-135 + 270 * share, R);
  const tick = polar(0, R + 15);

  return (
    <article className="glass flex h-full flex-col rounded-[28px] p-5">
      <h2 className="text-sm text-muted">{q.title}</h2>
      <div className="relative mx-auto mt-1 w-full max-w-[230px]">
        <svg viewBox="0 0 200 200" className="w-full" role="img" aria-label={`${q.title}: ${Math.round(share * 100)}%`}>
          <defs>
            <linearGradient id={`${id}-g`} x1="0" y1="1" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.5" />
              <stop offset="100%" stopColor={color} />
            </linearGradient>
          </defs>
          <g transform="rotate(135 100 100)">
            <circle cx="100" cy="100" r={R} fill="none" stroke="var(--border)" strokeWidth="14"
              strokeDasharray={`${C * ARC} ${C}`} strokeLinecap="round" />
            <circle cx="100" cy="100" r={R} fill="none" stroke={`url(#${id}-g)`} strokeWidth="14"
              strokeDasharray={`${C * ARC * share} ${C}`} strokeLinecap="round"
              style={{ transition: "stroke-dasharray .35s cubic-bezier(.2,.7,.2,1)" }} />
          </g>
          <circle cx={end.x} cy={end.y} r="9" fill="var(--surface-2)" stroke={color} strokeWidth="3"
            style={{ transition: "cx .35s, cy .35s" }} />
          <line x1="100" y1="12" x2="100" y2="34" stroke="var(--text-muted)" strokeWidth="1.5" strokeDasharray="2 3" />
          <text x={tick.x} y={tick.y - 2} textAnchor="middle" fill="var(--text-muted)" fontSize="9">50%</text>
          <circle cx="100" cy="100" r="50" fill="var(--surface-2)" stroke="var(--border)" />
          <text x="100" y="100" textAnchor="middle" className="fill-fg tabular" fontSize="30" fontWeight="600">
            {Math.round(share * 100)}%
          </text>
          <text x="100" y="119" textAnchor="middle" fill="var(--text-muted)" fontSize="10">{q.threshold}</text>
        </svg>
      </div>

      <p className="text-center text-sm font-semibold" style={{ color }} aria-live="polite">
        {ok ? q.ok : fill(q.no, { need })}
      </p>
      <p className="text-center text-xs text-muted tabular">{fill(q.caption, { n: count, total })}</p>

      <label htmlFor={`${id}-n`} className="sr-only">{q.slider}</label>
      <input
        id={`${id}-n`}
        type="range"
        min={0}
        max={total}
        value={count}
        onChange={(e) => setN(Number(e.target.value))}
        className="mt-4 w-full accent-[var(--warm)]"
      />
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-xs text-muted">{q.total}</span>
        <div className="flex items-center gap-1 rounded-full bg-surface-2 p-1">
          <button type="button" aria-label="−" onClick={() => setTotal((v) => Math.max(2, v - 10))}
            className="grid size-7 place-items-center rounded-full hover:bg-surface"><Minus className="size-3.5" /></button>
          <span className="w-10 text-center text-sm font-semibold tabular">{total}</span>
          <button type="button" aria-label="+" onClick={() => setTotal((v) => Math.min(990, v + 10))}
            className="grid size-7 place-items-center rounded-full hover:bg-surface"><Plus className="size-3.5" /></button>
        </div>
      </div>
      <p className="mt-4 text-xs leading-relaxed text-muted">{q.rule}</p>
      <Link href={href} className="mt-4 inline-flex items-center gap-1.5 self-start text-sm font-medium text-warm transition hover:gap-2.5">
        {t.calc.title}
        <ArrowRight className="size-4" />
      </Link>
    </article>
  );
}
