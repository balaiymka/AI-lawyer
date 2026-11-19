"use client";

import { ThemeProvider } from "next-themes";
import type { ReactNode } from "react";

// Тёмная тема по умолчанию (референс «билет»), светлая — «тёплое стекло».
export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
      {children}
    </ThemeProvider>
  );
}
