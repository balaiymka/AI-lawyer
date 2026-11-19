"use client";

import { clsx } from "clsx";
import type { CSSProperties, PointerEvent, ReactNode } from "react";

// Карточка с подсветкой, которая следует за курсором.
export function Spotlight({
  children,
  className,
  tint,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  tint?: string;
  as?: "div" | "button" | "article";
}) {
  function onMove(e: PointerEvent<HTMLElement>) {
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - r.left}px`);
    el.style.setProperty("--my", `${e.clientY - r.top}px`);
  }
  return (
    <Tag
      {...(Tag === "button" ? { type: "button" as const } : {})}
      onPointerMove={onMove}
      className={clsx("spotlight", className)}
      style={tint ? ({ "--tint": tint } as CSSProperties) : undefined}
    >
      {children}
    </Tag>
  );
}
