"use client";

import { clsx } from "clsx";
import { ArrowUp, Sparkles } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { Dictionary } from "@/lib/i18n";

type Role = "owner" | "osi" | "uk" | "lawyer";
const ROLES: Role[] = ["owner", "osi", "uk", "lawyer"];

// Печатает примеры вопросов по очереди, пока поле пустое.
function useTypewriter(lines: string[], active: boolean) {
  const [out, setOut] = useState("");
  useEffect(() => {
    if (!active) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setOut(lines[0]);
      return;
    }
    let line = 0;
    let pos = 0;
    let erasing = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      const full = lines[line];
      if (!erasing) {
        pos += 1;
        setOut(full.slice(0, pos));
        if (pos >= full.length) {
          erasing = true;
          timer = setTimeout(tick, 1900);
          return;
        }
        timer = setTimeout(tick, 38 + Math.random() * 40);
      } else {
        pos -= 2;
        setOut(full.slice(0, Math.max(pos, 0)));
        if (pos <= 0) {
          erasing = false;
          line = (line + 1) % lines.length;
          timer = setTimeout(tick, 350);
          return;
        }
        timer = setTimeout(tick, 18);
      }
    };
    timer = setTimeout(tick, 500);
    return () => clearTimeout(timer);
  }, [lines, active]);
  return out;
}

export function AskBox({ t }: { t: Dictionary }) {
  const [role, setRole] = useState<Role>("owner");
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const typed = useTypewriter(t.hero.examples, !text && !focused);
  const router = useRouter();
  const { locale } = useParams<{ locale: string }>();

  function submit() {
    const q = text.trim();
    if (q.length < 2) return;
    router.push(`/${locale}/chat?${new URLSearchParams({ q, role })}`);
  }

  return (
    <div className="glass glow-border relative rounded-[30px] p-3 shadow-[var(--shadow)] sm:p-4">
      <div className="flex items-center gap-2 overflow-x-auto pb-3 [scrollbar-width:none]">
        <span className="shrink-0 pl-1 text-xs text-muted">{t.roles.label}</span>
        <div role="radiogroup" className="flex shrink-0 rounded-full bg-surface-2 p-1">
          {ROLES.map((r) => (
            <button
              key={r}
              type="button"
              role="radio"
              aria-checked={role === r}
              onClick={() => setRole(r)}
              className={clsx(
                "whitespace-nowrap rounded-full px-3.5 py-1.5 text-[13px] font-medium transition",
                role === r ? "bg-accent text-accent-fg shadow-sm" : "text-muted hover:text-fg",
              )}
            >
              {t.roles[r]}
            </button>
          ))}
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="rounded-[22px] border border-line bg-surface-2 p-3 transition focus-within:border-warm/60"
      >
        <label htmlFor="ask" className="sr-only">
          {t.hero.placeholder}
        </label>
        <div className="relative">
          <textarea
            id="ask"
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={focused ? t.hero.placeholder : ""}
            className="relative z-10 w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none placeholder:text-muted"
          />
          {!text && !focused && (
            <p aria-hidden className="caret pointer-events-none absolute inset-0 text-[15px] leading-relaxed text-muted">
              {typed}
            </p>
          )}
        </div>
        <div className="mt-2 flex items-end justify-between gap-3">
          <p className="flex items-center gap-1.5 text-xs text-muted">
            <Sparkles className="size-3.5 text-warm" aria-hidden />
            {t.hero.live}
          </p>
          <button
            type="submit"
            disabled={text.trim().length < 2}
            className="flex shrink-0 items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-accent-fg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span className="hidden sm:inline">{t.hero.ask}</span>
            <ArrowUp className="size-4" aria-hidden />
          </button>
        </div>
      </form>

      <div className="flex gap-2 overflow-x-auto px-1 pt-3 [scrollbar-width:none]">
        {t.hero.chips.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setText(c)}
            className="shrink-0 rounded-full border border-line px-3 py-1.5 text-xs text-muted transition hover:border-warm/60 hover:text-fg"
          >
            {c}
          </button>
        ))}
      </div>
    </div>
  );
}
