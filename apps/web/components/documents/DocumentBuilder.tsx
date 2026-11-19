"use client";

import { clsx } from "clsx";
import { ArrowLeft, Check, Copy, Download, Lightbulb, MapPin, Printer } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AddressPicker } from "@/components/address/AddressPicker";
import { docToText, type FieldDef, type RenderedDoc, type TemplateDef } from "@/components/documents/types";
import { apiGet, apiPost, refLabel } from "@/lib/api";
import { API_URL } from "@/lib/chat";
import type { Dictionary, Locale } from "@/lib/i18n";

const STORE = "zhkh24-doc-values";

function loadSaved(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(STORE) ?? "{}");
  } catch {
    return {};
  }
}

function Input({ f, value, onChange }: { f: FieldDef; value: string; onChange: (v: string) => void }) {
  const cls = "w-full rounded-2xl border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none transition focus:border-warm/60";
  if (f.type === "textarea")
    return <textarea id={f.key} rows={3} value={value} placeholder={f.hint} onChange={(e) => onChange(e.target.value)} className={clsx(cls, "resize-y")} />;
  if (f.type === "select")
    return (
      <select id={f.key} value={value || f.options[0]?.value} onChange={(e) => onChange(e.target.value)} className={cls}>
        {f.options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  return (
    <input id={f.key} type={f.type} inputMode={f.type === "number" ? "numeric" : undefined} value={value} placeholder={f.hint}
      onChange={(e) => onChange(e.target.value)} className={cls} />
  );
}

export function DocumentBuilder({ code, t, locale }: { code: string; t: Dictionary; locale: Locale }) {
  const d = t.docs;
  const [tpl, setTpl] = useState<TemplateDef | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [doc, setDoc] = useState<RenderedDoc | null>(null);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [picker, setPicker] = useState(false);

  useEffect(() => {
    apiGet<TemplateDef>(`/v1/documents/templates/${code}?lang=${locale}`)
      .then((x) => {
        setTpl(x);
        // Общие поля (ФИО, адрес, ОСИ…) переносятся между документами.
        const saved = loadSaved();
        // У выпадающих списков сразу выбран первый вариант — он же попадает в документ.
        const defaults = Object.fromEntries(x.fields.filter((f) => f.type === "select" && f.options[0]).map((f) => [f.key, f.options[0].value]));
        const restored = Object.fromEntries(
          x.fields.filter((f) => saved[f.key] && (f.type !== "select" || f.options.some((o) => o.value === saved[f.key])))
            .map((f) => [f.key, saved[f.key]]),
        );
        setValues({ ...defaults, ...restored });
      })
      .catch(() => setError(true));
  }, [code, locale]);

  useEffect(() => {
    if (!tpl) return;
    const id = setTimeout(() => {
      apiPost<RenderedDoc>("/v1/documents/render", { code, lang: locale, values }).then(setDoc).catch(() => setError(true));
      try {
        localStorage.setItem(STORE, JSON.stringify({ ...loadSaved(), ...values }));
      } catch {}
    }, 250);
    return () => clearTimeout(id);
  }, [tpl, values, code, locale]);

  async function download() {
    const res = await fetch(`${API_URL}/v1/documents/docx`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code, lang: locale, values }),
    });
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${tpl?.title ?? "document"}.docx`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function copy() {
    if (!doc) return;
    await navigator.clipboard.writeText(docToText(doc));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (error) return <p className="glass rounded-[24px] p-5 text-sm text-danger">{d.apiError}</p>;

  return (
    <div className="space-y-5">
      <div className="no-print">
        <Link href={`/${locale}/documents`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
          <ArrowLeft className="size-4" />
          {d.back}
        </Link>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">{tpl?.title ?? "…"}</h1>
        {tpl && (
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            {tpl.description}
            {tpl.basis.map((b) => (
              <span key={b} className="rounded-full border border-success/40 px-2 py-0.5 text-[11px] text-success tabular">{refLabel(b, locale)}</span>
            ))}
          </p>
        )}
      </div>

      {picker && (
        <AddressPicker t={t} locale={locale} onClose={() => setPicker(false)}
          onPick={({ label, city }) => {
            setValues((s) => ({
              ...s,
              building_address: label,
              ...(tpl?.fields.some((f) => f.key === "city") && city && !s.city
                ? { city: locale === "kk" ? `${city} қаласының` : `г. ${city}` } : {}),
            }));
            setPicker(false);
          }} />
      )}

      <div className="print-block grid gap-5 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <form className="glass no-print h-fit space-y-4 rounded-[28px] p-5 lg:sticky lg:top-20" onSubmit={(e) => e.preventDefault()}>
          <h2 className="text-sm font-medium text-muted">{d.form}</h2>
          {tpl?.fields.map((f) => (
            <div key={f.key} className="space-y-1.5">
              <label htmlFor={f.key} className="flex items-center gap-1.5 text-sm font-medium">
                {f.label}
                {f.required && <span className="text-[11px] font-normal text-warm">· {d.required}</span>}
              </label>
              <Input f={f} value={values[f.key] ?? ""} onChange={(v) => setValues((s) => ({ ...s, [f.key]: v }))} />
              {f.key === "building_address" && (
                <button type="button" onClick={() => setPicker(true)}
                  className="flex items-center gap-1.5 text-xs font-medium text-warm hover:underline">
                  <MapPin className="size-3.5" />
                  {t.addr.find}
                </button>
              )}
            </div>
          ))}
          <p className="text-xs text-muted">{d.fillHint}</p>
        </form>

        <div className="space-y-3">
          <div className="no-print flex flex-wrap gap-2">
            <button type="button" onClick={download} className="flex items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-accent-fg transition hover:brightness-110">
              <Download className="size-4" />
              {d.download}
            </button>
            <button type="button" onClick={() => window.print()} className="flex items-center gap-2 rounded-full border border-line px-4 py-2.5 text-sm font-medium hover:bg-surface-2">
              <Printer className="size-4" />
              {d.print}
            </button>
            <button type="button" onClick={copy} className="flex items-center gap-2 rounded-full border border-line px-4 py-2.5 text-sm font-medium hover:bg-surface-2">
              {copied ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
              {copied ? d.copied : d.copy}
            </button>
          </div>

          {doc?.note && (
            <p className="no-print flex gap-2 rounded-2xl border border-warm/30 bg-warm/10 px-4 py-3 text-sm">
              <Lightbulb className="mt-0.5 size-4 shrink-0 text-warm" />
              <span><span className="font-medium">{d.tip}:</span> {doc.note}</span>
            </p>
          )}

          {/* Лист документа: всегда светлый, как бумага */}
          <article className="print-sheet rounded-[6px] bg-white px-6 py-8 font-serif text-[13.5px] leading-[1.55] text-neutral-900 shadow-[var(--shadow)] sm:px-12 sm:py-12">
            {doc ? (
              <>
                {(doc.to.length > 0 || doc.sender.length > 0) && (
                  <div className="ml-auto w-full space-y-3 sm:w-[55%]">
                    {doc.to.length > 0 && <div>{doc.to.map((l, i) => <p key={i}>{l}</p>)}</div>}
                    {doc.sender.length > 0 && <div>{doc.sender.map((l, i) => <p key={i}>{l}</p>)}</div>}
                  </div>
                )}
                <h2 className="mb-5 mt-8 whitespace-pre-line text-center font-bold">{doc.title}</h2>
                {doc.body.map((p, i) => <p key={i} className="indent-8 text-justify">{p}</p>)}
                {doc.requests.length > 0 && (
                  <>
                    <p className="mt-3 indent-8">{doc.requests_intro}</p>
                    {doc.requests.map((r, i) => <p key={i} className="indent-8 text-justify">{i + 1}) {r}</p>)}
                  </>
                )}
                {doc.attachments.length > 0 && (
                  <>
                    {doc.attachments_title.split("\n\n").map((x, i) => <p key={i} className="mt-3 indent-8 text-justify">{x}</p>)}
                    {doc.attachments.map((a, i) => <p key={i}>{i + 1}. {a}</p>)}
                  </>
                )}
                {doc.signature.length > 0 && <div className="mt-8">{doc.signature.map((s, i) => <p key={i}>{s}</p>)}</div>}
              </>
            ) : (
              <div className="space-y-3">
                {Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-3 animate-pulse rounded bg-neutral-200" style={{ width: `${60 + ((i * 17) % 40)}%` }} />)}
              </div>
            )}
          </article>
        </div>
      </div>
    </div>
  );
}
