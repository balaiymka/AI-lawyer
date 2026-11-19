"use client";

import { clsx } from "clsx";
import { Check, Download, FileArchive, FileText, ListChecks, Loader2, Paperclip, ShieldCheck, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { fill } from "@/lib/api";
import {
  autofillDraft, deleteDraft, deleteDraftFile, docxUrl, fmtSize, getDraft, patchDraft, uploadDraftFile, zipUrl,
  type Draft, type DraftField, type DraftSlot,
} from "@/lib/docs";
import type { Dictionary } from "@/lib/i18n";

type T = Dictionary["chat"]["doc"];
const input = "w-full rounded-2xl border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-electric/60";

function FieldInput({ f, value, onChange, onEnter, id }: {
  f: Pick<DraftField, "type" | "options" | "hint">; value: string; onChange: (v: string) => void; onEnter?: () => void; id: string;
}) {
  if (f.type === "select")
    return (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={input}>
        <option value="">—</option>
        {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
  if (f.type === "textarea")
    return <textarea id={id} rows={3} value={value} placeholder={f.hint} onChange={(e) => onChange(e.target.value)} className={input} />;
  return (
    <input
      id={id}
      type={f.type === "date" ? "date" : f.type === "number" ? "number" : "text"}
      inputMode={f.type === "number" ? "numeric" : undefined}
      value={value}
      placeholder={f.hint}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && onEnter) {
          e.preventDefault();
          onEnter();
        }
      }}
      className={input}
    />
  );
}

const shown = (f: DraftField) => (f.type === "select" ? f.options.find((o) => o.value === f.value)?.label ?? f.value : f.type === "date" && f.value ? f.value.split("-").reverse().join(".") : f.value);

function SlotRow({ slot, t, busy, onUpload, onRemove }: {
  slot: DraftSlot; t: T; busy: boolean; onUpload: (files: FileList) => void; onRemove: (id: string) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const done = slot.files.length > 0;
  return (
    <li className="rounded-2xl border border-line bg-surface/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={clsx("grid size-6 shrink-0 place-items-center rounded-full", done ? "bg-success/15 text-success" : "bg-surface-2 text-muted")}>
          {done ? <Check className="size-3.5" /> : <Paperclip className="size-3.5" />}
        </span>
        <span className="min-w-0 flex-1 text-sm font-medium">{slot.label}</span>
        <span className={clsx("rounded-full px-2 py-0.5 text-[10.5px] font-medium",
          slot.level === "required" ? "bg-danger/10 text-danger" : slot.level === "recommended" ? "bg-warm/15 text-warm" : "bg-surface-2 text-muted")}>
          {t.levels[slot.level]}
        </span>
        <input ref={ref} type="file" hidden multiple={slot.multiple} accept="application/pdf,image/jpeg,image/png,image/webp,image/heic,image/heif"
          onChange={(e) => {
            if (e.target.files?.length) onUpload(e.target.files);
            e.target.value = "";
          }} />
        <button type="button" disabled={busy} onClick={() => ref.current?.click()}
          className="rounded-full border border-line px-3 py-1 text-xs hover:bg-surface-2 disabled:opacity-50">
          {busy ? t.uploading : done && slot.multiple ? t.uploadMore : done ? t.edit : t.upload}
        </button>
      </div>
      {slot.files.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5 pl-8">
          {slot.files.map((f) => (
            <li key={f.id} className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-surface-2 py-1 pl-2.5 pr-1 text-[11px]">
              <span className="truncate">{f.name}</span>
              <span className="shrink-0 text-muted">{fmtSize(f.size)}</span>
              <button type="button" aria-label={t.remove} onClick={() => onRemove(f.id)} className="grid size-5 place-items-center rounded-full hover:bg-danger/15 hover:text-danger">
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

// Карточка документа в ленте чата: AI спрашивает недостающее по одному, просит приложения и отдаёт готовый пакет.
export function DocumentBuilder({ draftId, t, autofill, onDeleted }: { draftId: string; t: T; autofill?: boolean; onDeleted: () => void }) {
  const [d, setD] = useState<Draft | null>(null);
  const [answer, setAnswer] = useState("");
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [auto, setAuto] = useState<"running" | number | null>(null);
  const [busySlot, setBusySlot] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [gone, setGone] = useState(false);
  const started = useRef(false);

  const run = async (p: Promise<Draft>) => {
    setError(null);
    try {
      const next = await p;
      setD(next);
      return next;
    } catch (e) {
      setError((e as Error).message || t.error);
    }
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void run(getDraft(draftId)).then((first) => {
      if (!autofill || !first?.case_id) return;
      setAuto("running");
      autofillDraft(draftId)
        .then((x) => {
          setD(x);
          setAuto(x.filled_now?.length ?? 0);
        })
        .catch(() => setAuto(0));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftId]);

  useEffect(() => {
    const q = d?.next_question;
    setAnswer(q ? d.fields.find((f) => f.key === q.key)?.value ?? "" : "");
  }, [d?.next_question?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  if (gone) return <p className="text-sm text-muted">{t.deleted}</p>;
  if (!d) return <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="size-4 animate-spin" />{error ?? t.creating}</p>;

  const q = d.next_question;
  const filled = d.fields.filter((f) => f.filled);
  const missingAttach = d.attachments.filter((s) => s.level === "required" && !s.files.length);
  const showAttach = d.stage !== "fields";
  const pct = Math.round(((d.progress.required_filled + d.progress.attach_required_done) /
    Math.max(1, d.progress.required + d.progress.attach_required)) * 100);

  const submit = () => {
    if (!q || !answer.trim()) return;
    void run(patchDraft(d.id, { values: { [q.key]: answer.trim() } }));
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-warm/15 text-warm"><FileText className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{d.title}</p>
          <p className="text-xs text-muted tabular">
            {t.fields}: {d.progress.required_filled}/{d.progress.required} · {t.attachments}: {d.progress.attach_required_done}/{d.progress.attach_required}
          </p>
        </div>
        <span className="text-sm font-semibold tabular">{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-gradient-to-r from-electric to-lavender transition-all" style={{ width: `${pct}%` }} />
      </div>

      {auto !== null && (
        <p className="flex items-center gap-2 rounded-2xl bg-electric/10 px-3 py-2 text-xs text-electric">
          {auto === "running" ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
          {auto === "running" ? t.autofilling : auto > 0 ? fill(t.autofilled, { n: auto }) : t.autofillNone}
        </p>
      )}

      {filled.length > 0 && !form && (
        <details className="rounded-2xl border border-line px-3 py-2 text-sm">
          <summary className="cursor-pointer text-xs font-medium text-muted">{t.filledData} ({filled.length})</summary>
          <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            {filled.map((f) => (
              <div key={f.key} className="min-w-0">
                <dt className="text-muted">{f.label}{f.autofilled && <span className="ml-1 text-electric">· {t.fromChat}</span>}</dt>
                <dd className="truncate">{shown(f)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}

      {form ? (
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => {
          e.preventDefault();
          void run(patchDraft(d.id, { values: form })).then(() => setForm(null));
        }}>
          {d.fields.map((f) => (
            <div key={f.key} className={clsx("space-y-1", f.type === "textarea" && "sm:col-span-2")}>
              <label htmlFor={`df-${d.id}-${f.key}`} className="text-xs font-medium">{f.label}{f.required && <span className="text-danger"> *</span>}</label>
              <FieldInput id={`df-${d.id}-${f.key}`} f={f} value={form[f.key] ?? ""} onChange={(v) => setForm({ ...form, [f.key]: v })} />
            </div>
          ))}
          <div className="flex gap-2 sm:col-span-2">
            <button type="submit" className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg">{t.save}</button>
            <button type="button" onClick={() => setForm(null)} className="rounded-full border border-line px-4 py-2 text-sm">{t.chatMode}</button>
          </div>
        </form>
      ) : q ? (
        <div className="space-y-2">
          <p className="rounded-[18px] rounded-tl-md bg-surface-2 px-3.5 py-2.5 text-[15px]">
            {q.question}
            {!q.required && <span className="ml-1 text-xs text-muted">({t.optional})</span>}
          </p>
          <div className="flex flex-wrap items-start gap-2">
            <div className="min-w-[200px] flex-1">
              <label htmlFor={`dq-${d.id}`} className="sr-only">{q.question}</label>
              <FieldInput id={`dq-${d.id}`} f={q} value={answer} onChange={setAnswer} onEnter={submit} />
            </div>
            <button type="button" onClick={submit} disabled={!answer.trim()} className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40">{t.answer}</button>
            {!q.required && (
              <button type="button" onClick={() => void run(patchDraft(d.id, { skip: [q.key] }))} className="rounded-full border border-line px-4 py-2 text-sm hover:bg-surface-2">{t.skip}</button>
            )}
          </div>
        </div>
      ) : (
        <p className="flex items-center gap-2 text-sm text-success"><Check className="size-4" />{t.allFieldsDone}</p>
      )}

      {!form && (
        <button type="button" onClick={() => setForm(Object.fromEntries(d.fields.map((f) => [f.key, f.value])))}
          className="inline-flex items-center gap-1.5 text-xs text-muted underline-offset-2 hover:text-fg hover:underline">
          <ListChecks className="size-3.5" />{t.formMode}
        </button>
      )}

      {showAttach && d.attachments.length > 0 && (
        <div className="space-y-2 border-t border-line pt-4">
          <p className="text-sm">{t.attachIntro}</p>
          <ul className="space-y-2">
            {d.attachments.map((s) => (
              <SlotRow key={s.key} slot={s} t={t} busy={busySlot === s.key}
                onUpload={async (files) => {
                  setBusySlot(s.key);
                  for (const file of Array.from(files)) await run(uploadDraftFile(d.id, s.key, file));
                  setBusySlot(null);
                }}
                onRemove={(fid) => void run(deleteDraftFile(d.id, fid))} />
            ))}
          </ul>
          <p className="flex items-start gap-1.5 text-[11px] text-muted"><ShieldCheck className="mt-0.5 size-3.5 shrink-0" />{t.privacy}</p>
        </div>
      )}

      {error && <p className="rounded-xl bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}

      {(d.stage === "ready" || d.stage === "optional" || d.stage === "attachments") && (
        <div className="space-y-3 border-t border-line pt-4">
          <p className="text-sm">
            {missingAttach.length ? fill(t.readyMissing, { list: missingAttach.map((s) => s.label.toLowerCase()).join(", ") }) : t.ready}
          </p>
          <div className="flex flex-wrap gap-2">
            <a href={docxUrl(d.id)} className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg">
              <Download className="size-4" />{t.docx}
            </a>
            {d.attachments.some((s) => s.files.length) && (
              <a href={zipUrl(d.id)} className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm hover:bg-surface-2">
                <FileArchive className="size-4" />{t.zip}
              </a>
            )}
          </div>
        </div>
      )}

      <div className="flex justify-end">
        {confirmDelete ? (
          <span className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-danger">{t.deleteConfirm}</span>
            <button type="button" onClick={async () => {
              try {
                await deleteDraft(d.id);
                setGone(true);
                onDeleted();
              } catch {
                setError(t.error);
              }
            }} className="rounded-full bg-danger px-3 py-1 font-semibold text-white">{t.remove}</button>
            <button type="button" onClick={() => setConfirmDelete(false)} className="rounded-full border border-line px-3 py-1">✕</button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirmDelete(true)} className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-danger">
            <Trash2 className="size-3.5" />{t.delete}
          </button>
        )}
      </div>
    </div>
  );
}
