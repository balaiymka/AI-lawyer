"use client";

import { Gavel, Info } from "lucide-react";
import { useMemo, useState } from "react";

import { fmtDate as fmtD, fmtMonth as fmtM, fmtNumber, refLabel } from "@/lib/api";
import type { Dictionary, Locale } from "@/lib/i18n";

const DAY = 86_400_000;
const utc = (y: number, m: number, d: number) => Date.UTC(y, m, d);
const today = () => new Date().toISOString().slice(0, 10);
const thisMonth = () => new Date().toISOString().slice(0, 7);

function monthsBetween(from: string, to: string): [number, number][] {
  const [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  const out: [number, number][] = [];
  for (let y = fy, m = fm - 1; (y < ty || (y === ty && m <= tm - 1)) && out.length < 120; m++) {
    if (m > 11) { m = 0; y++; if (y > ty) break; }
    out.push([y, m]);
  }
  return out;
}

export function PenaltyCalculator({ t, locale }: { t: Dictionary; locale: Locale }) {
  const c = t.calc.penalty;
  const [fee, setFee] = useState(8000);
  const [from, setFrom] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 4);
    return d.toISOString().slice(0, 7);
  });
  const [to, setTo] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 1);
    return d.toISOString().slice(0, 7);
  });
  const [onDate, setOnDate] = useState(today);
  const [rate, setRate] = useState<string>("");

  const fmtMoney = fmtNumber;
  const fmtDate = (ms: number) => fmtD(ms);
  const fmtMonth = ([y, m]: [number, number]) => fmtM(y, m, locale);

  const r = Number(rate.replace(",", "."));
  const rows = useMemo(() => {
    const [cy, cm, cd] = onDate.split("-").map(Number);
    const calc = utc(cy, cm - 1, cd);
    return monthsBetween(from, to > thisMonth() ? thisMonth() : to).map(([y, m]) => {
      const due = utc(y, m + 1, 25); // до 25-го числа следующего месяца включительно (ст. 34-1 п. 8)
      const days = Math.max(0, Math.floor((calc - due) / DAY)); // пеня — со следующего дня (п. 9)
      const court = utc(y, m + 3, 25); // по истечении двух месяцев после даты платежа (п. 10)
      return { ym: [y, m] as [number, number], due, days, court, penalty: r > 0 ? (fee * r * days) / 100 : 0 };
    });
  }, [from, to, onDate, fee, r]);

  const debt = rows.length * fee;
  const pen = rows.reduce((s, x) => s + x.penalty, 0);
  const firstCourt = rows.find((x) => x.days > 0)?.court;
  const input = "w-full rounded-2xl border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-warm/60";

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
      <div className="glass h-fit space-y-4 rounded-[28px] p-5 sm:p-6">
        <div className="space-y-1.5">
          <label htmlFor="p-fee" className="text-sm font-medium">{c.fee}</label>
          <input id="p-fee" type="number" min={0} value={fee} onChange={(e) => setFee(Math.max(0, Number(e.target.value) || 0))} className={`${input} text-lg font-semibold tabular`} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label htmlFor="p-from" className="text-sm font-medium">{c.from}</label>
            <input id="p-from" type="month" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className={input} />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="p-to" className="text-sm font-medium">{c.to}</label>
            <input id="p-to" type="month" value={to} min={from} onChange={(e) => setTo(e.target.value)} className={input} />
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="p-date" className="text-sm font-medium">{c.date}</label>
          <input id="p-date" type="date" value={onDate} onChange={(e) => setOnDate(e.target.value || today())} className={input} />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="p-rate" className="text-sm font-medium">{c.rate}</label>
          <input id="p-rate" inputMode="decimal" placeholder="0,1" value={rate} onChange={(e) => setRate(e.target.value)} className={input} />
          <p className="flex gap-1.5 text-xs leading-relaxed text-warning"><Info className="mt-0.5 size-3.5 shrink-0" />{c.rateHint}</p>
        </div>
        <p className="rounded-2xl bg-surface-2 p-3 text-xs leading-relaxed text-muted">{c.dueRule}</p>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          {[[c.debt, debt], [c.penaltyTotal, pen], [c.total, debt + pen]].map(([label, v], i) => (
            <div key={i} className="glass rounded-[22px] p-4">
              <p className="text-xs text-muted">{label}</p>
              <p className={`mt-1 text-xl font-semibold tabular sm:text-2xl ${i === 2 ? "text-warm" : ""}`}>{fmtMoney(v as number)} ₸</p>
            </div>
          ))}
        </div>
        {!(r > 0) && <p className="text-sm text-warning">{c.enterRate}</p>}

        <div className="glass overflow-x-auto rounded-[24px]">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th className="px-4 py-3 font-medium">{c.month}</th>
                <th className="px-4 py-3 font-medium">{c.due}</th>
                <th className="px-4 py-3 text-right font-medium">{c.days}</th>
                <th className="px-4 py-3 text-right font-medium">{c.sum}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.ym.join("-")} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-2.5 first-letter:uppercase">{fmtMonth(x.ym)}</td>
                  <td className="px-4 py-2.5 tabular">{fmtDate(x.due)}</td>
                  <td className="px-4 py-2.5 text-right tabular">{x.days}</td>
                  <td className="px-4 py-2.5 text-right tabular">{fmtMoney(x.penalty)} ₸</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {firstCourt && (
          <p className="flex gap-2 rounded-2xl border border-line bg-surface p-4 text-sm">
            <Gavel className="mt-0.5 size-4 shrink-0 text-warm" />
            <span>{c.court}: <b className="tabular">{fmtDate(firstCourt)}</b> ({refLabel("art34-1/p10", locale)}). {c.noLimit}</span>
          </p>
        )}
        <p className="text-xs text-muted">{t.calc.info}</p>
      </div>
    </div>
  );
}
