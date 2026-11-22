"use client";

import { clsx } from "clsx";
import { Bot, BrainCircuit, Database, Library, RefreshCw, Server } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { ruDateTime } from "@/lib/admin";
import { fmtNumber } from "@/lib/api";
import { API_URL } from "@/lib/chat";

// Ответ GET /health (apps/api/app/routers/health.py)
type Health = {
  status: "ok" | "degraded" | "down";
  db: string;
  qdrant: { status: string; points?: number };
  laws: { status: string; acts?: number; versions?: number; current_versions?: number; last_fetched_at?: string | null };
  models: Record<"embedder" | "reranker", { name: string; loaded: boolean }>;
  llm: { provider: string; model: string; ready: boolean };
  took_ms: number;
};

type Level = "ok" | "warn" | "bad";
const level = (s: string): Level => (s === "ok" ? "ok" : s === "warning" || s === "skipped" ? "warn" : "bad");

const STATUS: Record<Health["status"], { label: string; lvl: Level }> = {
  ok: { label: "Всё работает", lvl: "ok" },
  degraded: { label: "Работает с ограничениями", lvl: "warn" },
  down: { label: "Поиск не работает", lvl: "bad" },
};

const PROVIDERS: Record<string, string> = {
  claude_code: "Claude Code (локально)",
  anthropic: "Claude API",
  gemini: "Gemini (Vertex AI)",
  none: "нет (демо-режим)",
};

const REFRESH_MS = 15000;
// Если законы не сверялись с Adilet дольше этого срока — подсвечиваем.
const STALE_DAYS = 7;

function Dot({ lvl }: { lvl: Level }) {
  return <span aria-hidden className={clsx("inline-block size-2.5 shrink-0 rounded-full",
    lvl === "ok" ? "bg-success" : lvl === "warn" ? "bg-warning" : "bg-danger")} />;
}

function Card({ icon, title, lvl, state, children }: { icon: ReactNode; title: string; lvl: Level; state: string; children?: ReactNode }) {
  return (
    <section className="glass space-y-2 rounded-[24px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold">{icon}{title}</div>
      <p className={clsx("flex items-center gap-2 text-sm", lvl === "ok" ? "text-success" : lvl === "warn" ? "text-warning" : "text-danger")}>
        <Dot lvl={lvl} />{state}
      </p>
      {children && <div className="space-y-0.5 text-xs text-muted">{children}</div>}
    </section>
  );
}

export function StatusPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [apiDown, setApiDown] = useState(false);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      // 503 тоже несёт JSON с подробностями — его не считаем ошибкой сети.
      const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
      setHealth((await res.json()) as Health);
      setApiDown(false);
    } catch {
      setApiDown(true);
    } finally {
      setCheckedAt(new Date());
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  const overall = apiDown ? { label: "API не отвечает", lvl: "bad" as Level } : health ? STATUS[health.status] : null;
  const laws = health?.laws;
  const lastFetch = laws?.last_fetched_at ? new Date(laws.last_fetched_at) : null;
  const staleDays = lastFetch ? Math.floor((Date.now() - lastFetch.getTime()) / 86400000) : null;

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Состояние системы</h1>
          <p className="text-sm text-muted">Проверка каждые {REFRESH_MS / 1000} секунд: база данных, поиск, законы, модели и языковая модель</p>
        </div>
        <button type="button" onClick={load} disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs hover:bg-surface-2 disabled:opacity-60">
          <RefreshCw className={clsx("size-3.5", busy && "animate-spin")} aria-hidden /> Проверить
        </button>
      </div>

      {overall && (
        <div role="status" className={clsx("glass flex flex-wrap items-center gap-3 rounded-[24px] px-5 py-4",
          overall.lvl === "bad" && "border-danger/50 bg-danger/10")}>
          <Dot lvl={overall.lvl} />
          <span className="font-semibold">{overall.label}</span>
          <span className="text-xs text-muted">
            {checkedAt && `проверено ${ruDateTime(checkedAt.toISOString())}`}
            {health && !apiDown && ` · ответ за ${health.took_ms} мс`}
          </span>
        </div>
      )}

      {apiDown && (
        <p className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
          Сервер API не запущен или недоступен. Проверьте процесс uvicorn и лог data/logs/api.log.
        </p>
      )}

      {health && !apiDown && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card icon={<Database className="size-4" aria-hidden />} title="PostgreSQL" lvl={level(health.db)}
            state={health.db === "ok" ? "Подключена" : health.db} />
          <Card icon={<Server className="size-4" aria-hidden />} title="Qdrant (векторный поиск)" lvl={level(health.qdrant.status)}
            state={health.qdrant.status === "ok" ? "Работает" : health.qdrant.status === "warning" ? "Коллекция пустая" : health.qdrant.status}>
            {health.qdrant.points != null && <p>Векторов: {fmtNumber(health.qdrant.points)}</p>}
          </Card>
          <Card icon={<Library className="size-4" aria-hidden />} title="База законов" lvl={staleDays != null && staleDays > STALE_DAYS ? "warn" : level(laws?.status ?? "error")}
            state={laws?.status === "ok" ? "Загружена" : laws?.status === "warning" ? "Не у всех актов есть действующая редакция" : laws?.status ?? "—"}>
            {laws?.acts != null && <p>Актов: {laws.acts} · редакций: {laws.versions} · действующих: {laws.current_versions}</p>}
            {lastFetch && (
              <p className={clsx(staleDays != null && staleDays > STALE_DAYS && "text-warning")}>
                Последняя сверка с Adilet: {ruDateTime(lastFetch.toISOString())} ({staleDays === 0 ? "сегодня" : `${staleDays} дн. назад`})
              </p>
            )}
          </Card>
          <Card icon={<BrainCircuit className="size-4" aria-hidden />} title="Модели поиска" lvl="ok"
            state={health.models.embedder.loaded && health.models.reranker.loaded ? "Загружены в память" : "Загрузятся при первом запросе"}>
            {Object.values(health.models).map((m) => <p key={m.name}>{m.name}: {m.loaded ? "в памяти" : "не загружена"}</p>)}
          </Card>
          <Card icon={<Bot className="size-4" aria-hidden />} title="Языковая модель" lvl={health.llm.ready ? "ok" : "bad"}
            state={health.llm.ready ? "Готова" : health.llm.provider === "claude_code" ? "Claude Code не найден" : health.llm.provider === "none" ? "Не подключена (демо-режим)" : "Не задан ключ или модель"}>
            <p>Провайдер: {PROVIDERS[health.llm.provider] ?? health.llm.provider}</p>
            <p>Модель: {health.llm.model === "default" ? "по умолчанию" : health.llm.model}</p>
          </Card>
        </div>
      )}
    </>
  );
}
