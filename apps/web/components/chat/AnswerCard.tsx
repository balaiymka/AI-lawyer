"use client";

import { clsx } from "clsx";
import {
  AlertTriangle,
  CalendarClock,
  ChevronDown,
  BadgeCheck,
  CircleHelp,
  ExternalLink,
  FileText,
  Calculator,
  Copy,
  Gavel,
  ListChecks,
  Scale,
  ShieldAlert,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { fill, fmtDate } from "@/lib/api";
import type { Analysis, Answer, Edition, Source, Verification } from "@/lib/chat";
import type { Dictionary } from "@/lib/i18n";

type T = Dictionary["chat"];

const VERDICT_COLOR = {
  yes: "var(--success)",
  no: "var(--danger)",
  partly: "var(--warm)",
  depends: "var(--electric)",
} as const;

const POSITION_COLOR = {
  strong: "var(--success)",
  moderate: "var(--warm)",
  weak: "var(--danger)",
  unclear: "var(--text-muted)",
} as const;

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="space-y-2.5">
      <h3 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-warm">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

export function CitationChip({ source, onClick, fallback }: { source?: Source; onClick?: () => void; fallback?: string }) {
  if (!source && !fallback) return null;
  const label = source
    ? [source.article && `ст. ${source.article}`, source.point && `п. ${source.point}`].filter(Boolean).join(" ") || source.path
    : fallback;
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-full border border-success/40 bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success transition hover:bg-success/20"
    >
      <BadgeCheck className="size-3" aria-hidden />
      {label}
    </button>
  );
}

export function AnswerCard({
  answer,
  verification,
  mode,
  notice,
  sources,
  t,
  onAsk,
  onFocusSource,
  onStartDoc,
  eventDate,
  eventPrecision,
  edition,
  analysis,
}: {
  analysis?: Analysis;
  onStartDoc?: (code: string) => void;
  eventDate?: string;
  eventPrecision?: string;
  edition?: Edition | null;
  answer: Answer;
  verification: Verification;
  mode: "llm" | "demo";
  notice?: string | null;
  sources: Source[];
  t: T;
  onAsk: (q: string) => void;
  onFocusSource: (chunkId: string) => void;
}) {
  const byId = new Map(sources.map((s) => [s.chunk_id, s]));
  const { locale } = useParams<{ locale: string }>();
  const pos = answer.assessment.position;

  return (
    <div className="space-y-5">
      {(mode === "demo" || notice) && (
        <p className="flex items-start gap-2 rounded-2xl border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
          <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
          {notice === "llm_failed" ? t.llmFailed : t.demo}
        </p>
      )}

      {answer.verdict && answer.verdict_text && (
        <div className="rounded-2xl border p-4" style={{ borderColor: `color-mix(in srgb, ${VERDICT_COLOR[answer.verdict]} 45%, transparent)`, background: `color-mix(in srgb, ${VERDICT_COLOR[answer.verdict]} 10%, transparent)` }}>
          <p className="font-[family-name:var(--font-unbounded)] text-lg font-semibold" style={{ color: VERDICT_COLOR[answer.verdict] }}>
            {t.verdicts[answer.verdict]}
          </p>
          <p className="mt-1 text-[15px] leading-relaxed">{answer.verdict_text}</p>
        </div>
      )}

      {eventDate && (
        <p className={clsx("inline-flex items-start gap-2 rounded-2xl border px-3 py-1.5 text-xs",
          edition && !edition.exact ? "border-warning/50 bg-warning/10 text-warning" : "border-line bg-surface")}>
          <CalendarClock className="mt-px size-3.5 shrink-0 text-electric" aria-hidden />
          {fill(edition && !edition.exact ? t.editionApprox : eventPrecision === "year" ? t.editionYear : t.edition, {
            date: fmtDate(eventDate),
            from: edition ? fmtDate(edition.valid_from) : "—",
          })}
        </p>
      )}

      <div>
        {answer.not_found && (
          <span className="mb-2 inline-flex rounded-full bg-surface px-2.5 py-1 text-[11px] font-medium text-muted">{t.notFound}</span>
        )}
        <p className="text-[15px] leading-relaxed">{answer.summary}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {mode === "llm" && (
            <span className="rounded-full px-2.5 py-1 text-[11px] font-semibold" style={{ color: POSITION_COLOR[pos], background: `color-mix(in srgb, ${POSITION_COLOR[pos]} 14%, transparent)` }}>
              {t.positions[pos]}
            </span>
          )}
          <span className={clsx("inline-flex items-center gap-1 text-[11px]", verification.needs_review ? "text-warning" : "text-success")}>
            {verification.needs_review ? <ShieldAlert className="size-3.5" aria-hidden /> : <BadgeCheck className="size-3.5" aria-hidden />}
            {verification.needs_review ? t.review : t.verified}
          </span>
          {analysis?.fact_check && analysis.fact_check.verdict !== "error" && (
            <span className="inline-flex items-center gap-1 text-[11px] text-success"
              title={analysis.fact_check.issues.map((i) => `${i.problem} → ${i.correction}`).join("\n") || undefined}>
              <BadgeCheck className="size-3.5" aria-hidden />
              {analysis.fact_check.revised ? t.factFixed : t.factChecked}
            </span>
          )}
          {analysis && analysis.sub_questions.length > 1 && (
            <span className="text-[11px] text-muted">{t.subQuestions}: {analysis.sub_questions.length}</span>
          )}
        </div>
      </div>

      {answer.legal_answer && (
        <details className="group rounded-2xl border border-line bg-surface p-4">
          <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold">
            <span className="flex items-center gap-2"><Gavel className="size-4 text-electric" aria-hidden />{t.legal}</span>
            <ChevronDown className="size-4 transition group-open:rotate-180" aria-hidden />
          </summary>
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-fg/90">{answer.legal_answer}</p>
        </details>
      )}

      {(answer.calculations ?? []).length > 0 && (
        <Section icon={<Calculator className="size-3.5" />} title={t.calculations}>
          <ul className="space-y-2">
            {answer.calculations!.map((x, i) => (
              <li key={i} className="rounded-2xl border border-line bg-surface p-4 text-sm">
                <p className="font-medium">{x.item}</p>
                <p className="mt-1 text-muted">{x.rule}</p>
                <p className="mt-2 whitespace-pre-line font-medium text-fg">{x.result}</p>
                {x.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {x.citations.map((c) => <CitationChip key={c} source={byId.get(c)} onClick={() => onFocusSource(c)} />)}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(answer.drafts ?? []).length > 0 && (
        <Section icon={<FileText className="size-3.5" />} title={t.drafts}>
          {answer.drafts!.map((d, i) => (
            <div key={i} className="rounded-2xl border border-line bg-surface p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium">{d.title}</p>
                <button type="button" onClick={() => void navigator.clipboard?.writeText(d.text)}
                  className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[11px] text-muted hover:text-fg">
                  <Copy className="size-3" aria-hidden />{t.copy}
                </button>
              </div>
              <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-fg/90">{d.text}</p>
            </div>
          ))}
        </Section>
      )}

      {answer.legal_basis.length > 0 && (
        <Section icon={<Scale className="size-3.5" />} title={t.basis}>
          <ul className="space-y-3">
            {answer.legal_basis.map((b) => {
              const src = byId.get(b.chunk_id);
              return (
                <li key={b.chunk_id} className="rounded-2xl border border-line bg-surface p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CitationChip source={src} onClick={() => onFocusSource(b.chunk_id)}
                      fallback={b.article ? `ст. ${b.article}${b.point ? ` п. ${b.point}` : ""}` : undefined} />
                    {src?.url && (
                      <a href={src.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] text-muted hover:text-fg">
                        {t.openAdilet}
                        <ExternalLink className="size-3" aria-hidden />
                      </a>
                    )}
                  </div>
                  <blockquote className="mt-3 border-l-2 border-warm/60 pl-3 text-sm leading-relaxed text-fg/90">{b.quote}</blockquote>
                  {!b.quote_verified && <p className="mt-1.5 text-[11px] text-warning">{t.quoteReplaced}</p>}
                  {b.explanation && <p className="mt-2 text-sm text-muted">{b.explanation}</p>}
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      {answer.responsibility.length > 0 && (
        <Section icon={<Users className="size-3.5" />} title={t.responsibility}>
          <ul className="space-y-2">
            {answer.responsibility.map((r) => (
              <li key={r.party} className="rounded-2xl bg-surface p-3 text-sm">
                <p className="font-medium">
                  {r.party} <span className="text-xs font-normal text-muted">· {t.liability[r.liability_type]}</span>
                </p>
                <p className="mt-1 text-muted">{r.reason}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {r.citations.map((c) => <CitationChip key={c} source={byId.get(c)} onClick={() => onFocusSource(c)} />)}
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {mode === "llm" && (answer.assessment.reasoning || answer.assessment.risks.length > 0) && (
        <Section icon={<Gavel className="size-3.5" />} title={t.assessment}>
          <p className="text-sm leading-relaxed">{answer.assessment.reasoning}</p>
          {answer.assessment.risks.length > 0 && (
            <ul className="space-y-1 text-sm text-muted">
              {answer.assessment.risks.map((r) => (
                <li key={r} className="flex gap-2"><span className="text-danger">•</span>{r}</li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {answer.action_plan.length > 0 && (
        <Section icon={<ListChecks className="size-3.5" />} title={t.plan}>
          <ol className="relative space-y-4 before:absolute before:bottom-2 before:left-[13px] before:top-2 before:w-px before:bg-line">
            {answer.action_plan.map((s, i) => (
              <li key={i} className="relative flex gap-3">
                <span className="relative grid size-7 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-fg tabular">{i + 1}</span>
                <div className="min-w-0 flex-1 text-sm">
                  <p className="font-medium leading-snug">{s.step}</p>
                  <dl className="mt-1.5 grid gap-x-4 gap-y-1 text-xs text-muted sm:grid-cols-2">
                    {s.who && <div><dt className="inline">{t.who}: </dt><dd className="inline text-fg/80">{s.who}</dd></div>}
                    {s.where && <div><dt className="inline">{t.where}: </dt><dd className="inline text-fg/80">{s.where}</dd></div>}
                    {s.deadline && <div><dt className="inline">{t.deadline}: </dt><dd className="inline text-fg/80">{s.deadline}</dd></div>}
                    {s.evidence.length > 0 && <div className="sm:col-span-2"><dt className="inline">{t.evidence}: </dt><dd className="inline text-fg/80">{s.evidence.join(", ")}</dd></div>}
                  </dl>
                  {s.citations.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {s.citations.map((c) => <CitationChip key={c} source={byId.get(c)} onClick={() => onFocusSource(c)} />)}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {answer.documents.length > 0 && (
        <Section icon={<FileText className="size-3.5" />} title={t.documents}>
          <div className="flex flex-wrap gap-2">
            {answer.documents.map((d) => (
              <span key={d} className="inline-flex items-center overflow-hidden rounded-full border border-line bg-surface text-xs font-medium">
                {onStartDoc ? (
                  <button type="button" onClick={() => onStartDoc(d)} className="inline-flex items-center gap-1.5 px-3 py-1.5 transition hover:bg-warm/10">
                    <FileText className="size-3.5 text-warm" aria-hidden />
                    {t.templates[d as keyof T["templates"]] ?? d}
                    <span className="text-warm">· {t.doc.start}</span>
                  </button>
                ) : (
                  <Link href={`/${locale}/documents/${d}`} className="inline-flex items-center gap-1.5 px-3 py-1.5 transition hover:bg-warm/10">
                    <FileText className="size-3.5 text-warm" aria-hidden />
                    {t.templates[d as keyof T["templates"]] ?? d}
                  </Link>
                )}
              </span>
            ))}
          </div>
        </Section>
      )}

      {answer.assumptions.length > 0 && (
        <p className="text-xs text-muted"><span className="font-medium">{t.assumptions}:</span> {answer.assumptions.join("; ")}</p>
      )}

      {answer.clarifying_questions.length > 0 && (
        <Section icon={<CircleHelp className="size-3.5" />} title={t.questions}>
          <div className="flex flex-wrap gap-2">
            {answer.clarifying_questions.map((q) => (
              <button key={q} type="button" onClick={() => onAsk(q)} className="rounded-full border border-line px-3 py-1.5 text-left text-xs transition hover:border-warm/60">
                {q}
              </button>
            ))}
          </div>
        </Section>
      )}

      <p className="border-t border-line pt-3 text-[11px] text-muted">{answer.disclaimer}</p>
    </div>
  );
}
