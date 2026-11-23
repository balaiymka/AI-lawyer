"use client";

import { clsx } from "clsx";
import { ArrowUp, BookOpen, Check, ChevronDown, FileText, Loader2, Plus, Square } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AnswerCard } from "@/components/chat/AnswerCard";
import { DocumentBuilder } from "@/components/chat/DocumentBuilder";
import { SourcesPanel } from "@/components/chat/SourcesPanel";
import { apiGet } from "@/lib/api";
import { partialSummary, streamChat, type Analysis, type Answer, type Edition, type Role, type Source, type Verification } from "@/lib/chat";
import { createDraft, listDrafts } from "@/lib/docs";
import type { Dictionary } from "@/lib/i18n";

type Stage = "normalize" | "search" | "answer" | "factcheck";
const STAGES: Stage[] = ["normalize", "search", "answer", "factcheck"];

type Turn = {
  id: number;
  q: string;
  stage: Stage | "done";
  raw: string;
  sources: Source[];
  answer?: Answer;
  verification?: Verification;
  mode?: "llm" | "demo";
  notice?: string | null;
  error?: boolean;
  eventDate?: string;
  eventPrecision?: string;
  edition?: Edition | null;
  analysis?: Analysis;
};

function Progress({ stage, t }: { stage: Turn["stage"]; t: Dictionary["chat"] }) {
  const idx = stage === "done" ? STAGES.length : STAGES.indexOf(stage);
  return (
    <ol className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
      {STAGES.map((s, i) => (
        <li key={s} className={clsx("flex items-center gap-1.5", i <= idx ? "text-fg" : "text-muted/60")}>
          {i < idx ? <Check className="size-3.5 text-success" /> : i === idx ? <Loader2 className="size-3.5 animate-spin text-warm" /> : <span className="size-3.5 rounded-full border border-line" />}
          {t.stages[s]}
        </li>
      ))}
    </ol>
  );
}

type DocTurn = { id: string; anchor: number | null; autofill: boolean };

type SavedCase = {
  id: string;
  messages: { role: "user" | "assistant"; text: string | null; answer: (Answer & { _meta?: { mode?: "llm" | "demo"; verification?: Verification; sources?: Source[]; analysis?: Analysis } }) | null }[];
};

const NO_ISSUES: Verification = { removed_citations: [], replaced_quotes: 0, unverified_refs: [], needs_review: false };

export function ChatView({ t, initialQ, role, initialCase }: { t: Dictionary; initialQ?: string; role?: Role; initialCase?: string }) {
  const c = t.chat;
  const { locale } = useParams<{ locale: string }>();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [docs, setDocs] = useState<DocTurn[]>([]);
  const [mobileSources, setMobileSources] = useState<number | null>(null); // на телефоне — источники под ответом
  const [docMenu, setDocMenu] = useState(false);
  const [docBusy, setDocBusy] = useState(false);
  const [docError, setDocError] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const started = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);

  const patch = (id: number, p: Partial<Turn> | ((t: Turn) => Partial<Turn>)) =>
    setTurns((ts) => ts.map((x) => (x.id === id ? { ...x, ...(typeof p === "function" ? p(x) : p) } : x)));

  // Документ в чате: черновик привязан к делу, AI дозаполняет его из переписки и спрашивает остальное.
  const startDoc = async (code: string, anchor: number | null) => {
    setDocMenu(false);
    setDocBusy(true);
    setDocError(false);
    try {
      const d = await createDraft(code, locale === "kk" ? "kk" : "ru", caseId);
      setDocs((ds) => [...ds, { id: d.id, anchor, autofill: Boolean(caseId) }]);
      setTimeout(() => document.getElementById(`doc-${d.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch {
      setDocError(true);
    } finally {
      setDocBusy(false);
    }
  };

  const send = useCallback(
    async (q: string) => {
      q = q.trim();
      if (q.length < 2 || busy) return;
      const id = Date.now();
      const history = turns.flatMap((x) => [
        { role: "user" as const, text: x.q },
        ...(x.answer ? [{ role: "assistant" as const, text: x.answer.summary }] : []),
      ]);
      setTurns((ts) => [...ts, { id, q, stage: "normalize", raw: "", sources: [] }]);
      setText("");
      setBusy(true);
      setFocused(null);
      abort.current = new AbortController();
      try {
        await streamChat(
          { q, role, case_id: caseId, history },
          (e) => {
            switch (e.event) {
              case "status":
                return patch(id, { stage: e.data.stage });
              case "sources":
                return patch(id, { sources: e.data.sources });
              case "delta":
                return patch(id, (x) => ({ raw: x.raw + e.data.text }));
              case "notice":
                return patch(id, { notice: e.data.code });
              case "answer":
                return patch(id, { answer: e.data.answer, verification: e.data.verification, mode: e.data.mode, stage: "done",
                  eventDate: e.data.event_date || undefined, eventPrecision: e.data.event_date_precision || undefined,
                  edition: e.data.edition ?? null, analysis: e.data.analysis });
              case "error":
                return patch(id, { error: true, stage: "done" });
              case "done":
                if (e.data.case_id) setCaseId(e.data.case_id);
            }
          },
          abort.current.signal,
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") patch(id, { error: true, stage: "done" });
        else patch(id, { stage: "done" });
      } finally {
        setBusy(false);
      }
    },
    [busy, turns, role, caseId],
  );

  useEffect(() => {
    if (!initialCase || started.current) return;
    started.current = true;
    apiGet<SavedCase>(`/v1/cases/${initialCase}`)
      .then((c) => {
        const out: Turn[] = [];
        c.messages.forEach((m, i) => {
          if (m.role === "user") out.push({ id: i, q: m.text ?? "", stage: "done", raw: "", sources: [] });
          else if (m.answer && out.length) {
            const { _meta, ...answer } = m.answer;
            Object.assign(out[out.length - 1], {
              answer, mode: _meta?.mode ?? "demo", verification: _meta?.verification ?? NO_ISSUES, sources: _meta?.sources ?? [],
              analysis: _meta?.analysis,
            });
          }
        });
        setTurns(out);
        setCaseId(c.id);
        listDrafts(c.id)
          .then((ds) => setDocs(ds.map((d) => ({ id: d.id, anchor: null, autofill: false }))))
          .catch(() => {});
      })
      .catch(() => setTurns([{ id: 0, q: "…", stage: "done", raw: "", sources: [], error: true }]));
  }, [initialCase]);

  useEffect(() => {
    if (initialQ && !started.current) {
      started.current = true;
      void send(initialQ);
    }
  }, [initialQ, send]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, turns.at(-1)?.stage]);

  const last = turns.at(-1);
  const sources = last?.sources ?? [];
  const cited = new Set(last?.answer?.legal_basis.map((b) => b.chunk_id) ?? []);

  const reset = () => {
    abort.current?.abort();
    setTurns([]);
    setCaseId(null);
    setDocs([]);
  };

  const docCard = (dt: DocTurn) => (
    <div key={dt.id} id={`doc-${dt.id}`} className="rise flex scroll-mt-24 gap-3">
      <span className="ai-orb mt-1 size-8 shrink-0" aria-hidden />
      <div className="glass min-w-0 flex-1 rounded-[24px] rounded-tl-md border border-warm/30 p-4 sm:p-5">
        <DocumentBuilder draftId={dt.id} t={c.doc} autofill={dt.autofill} onDeleted={() => {}} />
      </div>
    </div>
  );

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex min-h-[calc(100dvh-9rem)] flex-col">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-3 text-2xl font-semibold tracking-tight sm:text-3xl"><span className="ai-orb size-9 shrink-0" aria-hidden />{c.title}</h1>
            <p className="mt-1 text-sm text-muted">{c.subtitle}</p>
          </div>
          {turns.length > 0 && (
            <button type="button" onClick={reset} className="flex shrink-0 items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs hover:bg-surface-2">
              <Plus className="size-3.5" />
              {c.newChat}
            </button>
          )}
        </div>

        <div className="flex-1 space-y-6">
          {turns.length === 0 && (
            <div className="glass rounded-[28px] p-6">
              <p className="font-medium">{c.emptyTitle}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {[...t.hero.chips, ...t.hero.examples.slice(0, 2)].map((q) => (
                  <button key={q} type="button" onClick={() => send(q)} className="rounded-full border border-line px-3 py-1.5 text-left text-sm transition hover:border-warm/60">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn) => {
            const streaming = partialSummary(turn.raw);
            return (
              <div key={turn.id} className="space-y-3">
                <p className="rise ml-auto w-fit max-w-[85%] rounded-[20px] rounded-br-md bg-accent px-4 py-3 text-[15px] text-accent-fg">{turn.q}</p>
                <div className="rise flex gap-3">
                  <span className="ai-orb mt-1 size-8 shrink-0" aria-hidden />
                  <div className="glass min-w-0 flex-1 rounded-[24px] rounded-tl-md p-4 sm:p-5">
                    {turn.answer && turn.verification && turn.mode ? (
                      <AnswerCard
                        answer={turn.answer}
                        verification={turn.verification}
                        mode={turn.mode}
                        notice={turn.notice}
                        sources={turn.sources}
                        t={c}
                        onAsk={send}
                        onFocusSource={(id) => {
                          setFocused(id);
                          // на телефоне правой панели нет: раскрываем источники прямо под этим ответом
                          if (window.matchMedia("(max-width: 1023px)").matches) setMobileSources(turn.id);
                        }}
                        onStartDoc={(code) => void startDoc(code, turn.id)}
                        eventDate={turn.eventDate}
                        eventPrecision={turn.eventPrecision}
                        edition={turn.edition}
                        analysis={turn.analysis}
                      />
                    ) : turn.error ? (
                      <p className="text-sm text-danger">{c.error}</p>
                    ) : (
                      <div className="space-y-3">
                        <Progress stage={turn.stage} t={c} />
                        {streaming && <p className="caret text-[15px] leading-relaxed">{streaming}</p>}
                      </div>
                    )}
                  </div>
                </div>
                {turn.answer && turn.sources.length > 0 && (
                  <div className="pl-11 lg:hidden">
                    <button type="button" onClick={() => setMobileSources((v) => (v === turn.id ? null : turn.id))}
                      aria-expanded={mobileSources === turn.id}
                      className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-2 text-xs font-medium">
                      <BookOpen className="size-3.5 text-warm" aria-hidden />
                      {c.sources} ({turn.sources.length})
                      <ChevronDown className={clsx("size-3.5 transition", mobileSources === turn.id && "rotate-180")} aria-hidden />
                    </button>
                    {mobileSources === turn.id && (
                      <div className="mt-2">
                        <SourcesPanel sources={turn.sources} cited={new Set(turn.answer.legal_basis.map((b) => b.chunk_id))}
                          focused={focused} t={c} />
                      </div>
                    )}
                  </div>
                )}
                {docs.filter((dt) => dt.anchor === turn.id).map(docCard)}
              </div>
            );
          })}
          {docs.filter((dt) => dt.anchor === null || !turns.some((x) => x.id === dt.anchor)).map(docCard)}
          {docBusy && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="size-4 animate-spin" />{c.doc.creating}</p>}
          {docError && <p className="text-sm text-danger">{c.doc.error}</p>}
          <div ref={bottom} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(text);
          }}
          className="glass glow-border sticky bottom-24 mt-6 flex items-end gap-2 rounded-[26px] p-2 shadow-[var(--shadow)] md:bottom-4"
        >
          <div className="relative">
            <button type="button" onClick={() => setDocMenu((v) => !v)} aria-expanded={docMenu} aria-label={c.doc.newDoc}
              className="grid size-11 place-items-center rounded-full text-muted transition hover:bg-surface-2 hover:text-fg">
              <FileText className="size-5" />
            </button>
            {docMenu && (
              <div className="glass absolute bottom-14 left-0 z-20 w-72 rounded-[20px] p-2 shadow-[var(--shadow)]">
                <p className="px-2 pb-1 pt-1 text-xs font-medium text-muted">{c.doc.pick}</p>
                {Object.entries(c.templates).map(([code, label]) => (
                  <button key={code} type="button" onClick={() => void startDoc(code, null)}
                    className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left text-sm hover:bg-surface-2">
                    <FileText className="size-4 shrink-0 text-warm" />{label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <label htmlFor="chat-input" className="sr-only">{c.placeholder}</label>
          <textarea
            id="chat-input"
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(text);
              }
            }}
            placeholder={c.placeholder}
            className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] outline-none [field-sizing:content] placeholder:text-muted"
          />
          {busy ? (
            <button type="button" onClick={() => abort.current?.abort()} aria-label={c.stop} className="grid size-11 place-items-center rounded-full bg-surface-2">
              <Square className="size-4" />
            </button>
          ) : (
            <button type="submit" aria-label={c.send} disabled={text.trim().length < 2} className="grid size-11 place-items-center rounded-full bg-accent text-accent-fg transition disabled:opacity-40">
              <ArrowUp className="size-5" />
            </button>
          )}
        </form>
      </div>

      <div className="hidden lg:block">
        <div className="sticky top-20">
          <SourcesPanel sources={sources} cited={cited} focused={focused} t={c} />
        </div>
      </div>
    </div>
  );
}
