"use client";

import { clsx } from "clsx";
import { BadgeCheck, CircleX } from "lucide-react";
import { useState } from "react";

import { Meter } from "@/components/calculators/Meter";
import { fill } from "@/lib/api";
import type { Dictionary } from "@/lib/i18n";

type Kind = "general" | "special" | "entrance";

function Num({ id, label, value, onChange, max }: { id: string; label: string; value: number; onChange: (n: number) => void; max?: number }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <input id={id} type="number" min={0} max={max} inputMode="numeric" value={Number.isFinite(value) ? value : ""}
        onChange={(e) => onChange(Math.max(0, Math.floor(Number(e.target.value) || 0)))}
        className="w-full rounded-2xl border border-line bg-surface-2 px-3.5 py-2.5 text-lg font-semibold tabular outline-none focus:border-warm/60" />
    </div>
  );
}

// «Больше половины» от n: минимальное целое число, строго большее n/2.
const moreThan = (n: number, share: number) => Math.floor(n * share) + 1;

export function QuorumCalculator({ t }: { t: Dictionary }) {
  const q = t.calc.quorum;
  const [kind, setKind] = useState<Kind>("general");
  const [total, setTotal] = useState(120);
  const [present, setPresent] = useState(70);
  const [yes, setYes] = useState(40);

  const p = Math.min(present, total);
  const y = Math.min(yes, kind === "entrance" ? total : p);
  const quorumNeed = moreThan(total, 1 / 2);
  const quorumOk = kind === "entrance" ? true : p >= quorumNeed;
  const base = kind === "general" ? p : total; // от чего считается большинство
  const share = kind === "entrance" ? 2 / 3 : 1 / 2;
  const votesNeed = moreThan(base, share);
  const passed = quorumOk && y >= votesNeed && total > 0;
  const rule = { general: q.ruleGeneral, special: q.ruleSpecial, entrance: q.ruleEntrance }[kind];

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="glass space-y-5 rounded-[28px] p-5 sm:p-6">
        <div>
          <p className="mb-2 text-sm font-medium">{q.type}</p>
          <div role="radiogroup" className="flex flex-wrap gap-2">
            {(["general", "special", "entrance"] as Kind[]).map((k) => (
              <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
                className={clsx("rounded-full px-3.5 py-1.5 text-[13px] font-medium transition",
                  kind === k ? "bg-accent text-accent-fg" : "border border-line text-muted hover:text-fg")}>
                {q.types[k]}
              </button>
            ))}
          </div>
        </div>
        <Num id="q-total" label={kind === "entrance" ? q.totalEntrance : q.total} value={total} onChange={setTotal} />
        {kind !== "entrance" && <Num id="q-present" label={q.participants} value={present} onChange={setPresent} max={total} />}
        <Num id="q-yes" label={q.votesFor} value={yes} onChange={setYes} />
        <p className="rounded-2xl bg-surface-2 p-3 text-xs leading-relaxed text-muted">{rule}</p>
      </div>

      <div className="glass space-y-6 rounded-[28px] p-5 sm:p-6" aria-live="polite">
        {kind !== "entrance" && (
          <section className="space-y-3">
            <p className={clsx("flex items-center gap-2 text-lg font-semibold", quorumOk ? "text-success" : "text-warm")}>
              {quorumOk ? <BadgeCheck className="size-5" /> : <CircleX className="size-5" />}
              {quorumOk ? q.quorumOk : q.quorumNo}
              {!quorumOk && <span className="text-sm font-normal text-muted">— {fill(q.needMore, { n: quorumNeed - p })}</span>}
            </p>
            <Meter value={p} max={total} threshold={total / 2} ok={quorumOk} label={`${p} / ${total} · ${fill(q.threshold, { n: total / 2 })}`} />
          </section>
        )}
        <section className="space-y-3">
          <p className={clsx("flex items-center gap-2 text-lg font-semibold", passed ? "text-success" : "text-warm")}>
            {passed ? <BadgeCheck className="size-5" /> : <CircleX className="size-5" />}
            {passed ? q.passed : q.failed}
            {quorumOk && !passed && <span className="text-sm font-normal text-muted">— {fill(q.needVotes, { n: votesNeed - y })}</span>}
          </p>
          <Meter value={y} max={base} threshold={base * share} ok={passed}
            label={`${y} / ${base} · ${fill(q.threshold, { n: Math.round(base * share * 100) / 100 })}`} />
        </section>
        <p className="text-xs text-muted">{t.calc.info}</p>
      </div>
    </div>
  );
}
