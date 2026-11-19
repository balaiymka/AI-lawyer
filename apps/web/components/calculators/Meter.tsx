// Полоса «значение против порога»: заливка до значения, вертикальная метка на пороге.
export function Meter({ value, max, threshold, ok, label }: { value: number; max: number; threshold: number; ok: boolean; label: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const th = max > 0 ? Math.min(100, (threshold / max) * 100) : 0;
  const color = ok ? "var(--success)" : "var(--warm)";
  return (
    <div>
      <div className="relative h-3 rounded-full bg-surface-2">
        <div className="h-full rounded-full transition-[width] duration-300" style={{ width: `${pct}%`, background: color }} />
        <div className="absolute -top-1 h-5 w-0.5 rounded bg-fg/70" style={{ left: `calc(${th}% - 1px)` }} aria-hidden />
      </div>
      <p className="mt-1.5 text-right text-[11px] text-muted tabular">{label}</p>
    </div>
  );
}
