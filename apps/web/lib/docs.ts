// Навык «Документ в чате»: черновик в деле, вопросы по полям, приложения, выгрузка.

import { API_URL } from "@/lib/chat";

export type DraftField = {
  key: string; label: string; type: "text" | "textarea" | "date" | "number" | "select"; required: boolean; hint: string;
  options: { value: string; label: string }[]; value: string; filled: boolean; autofilled: boolean; skipped: boolean;
};
export type DraftFile = { id: string; name: string; size: number; mime: string };
export type DraftSlot = { key: string; label: string; level: "required" | "recommended" | "optional"; multiple: boolean; files: DraftFile[] };
export type Draft = {
  id: string; case_id: string | null; code: string; title: string; lang: "ru" | "kk"; fields: DraftField[];
  next_question: { key: string; question: string; type: DraftField["type"]; required: boolean; options: DraftField["options"]; hint: string } | null;
  attachments: DraftSlot[]; stage: "fields" | "attachments" | "optional" | "ready";
  progress: { required: number; required_filled: number; attach_required: number; attach_required_done: number };
  filled_now?: string[];
};

const base = `${API_URL}/v1/documents/drafts`;

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

const send = <T,>(path: string, method: string, body?: unknown) =>
  fetch(`${base}${path}`, { method, headers: body ? { "content-type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined }).then(json<T>);

export const createDraft = (code: string, lang: string, caseId: string | null) =>
  send<Draft>("", "POST", { code, lang, case_id: caseId, known: {} });
export const getDraft = (id: string) => send<Draft>(`/${id}`, "GET");
export const listDrafts = (caseId: string) => fetch(`${base}?case_id=${encodeURIComponent(caseId)}`).then(json<Draft[]>);
export const patchDraft = (id: string, body: { values?: Record<string, string>; skip?: string[] }) => send<Draft>(`/${id}`, "PATCH", body);
export const autofillDraft = (id: string) => send<Draft>(`/${id}/autofill`, "POST");
export const deleteDraft = (id: string) => send<{ deleted: boolean }>(`/${id}`, "DELETE");
export const deleteDraftFile = (id: string, fileId: string) => send<Draft>(`/${id}/files/${fileId}`, "DELETE");
export function uploadDraftFile(id: string, slot: string, file: File) {
  const fd = new FormData();
  fd.append("slot", slot);
  fd.append("file", file);
  return fetch(`${base}/${id}/files`, { method: "POST", body: fd }).then(json<Draft>);
}
export const docxUrl = (id: string) => `${base}/${id}/docx`;
export const zipUrl = (id: string) => `${base}/${id}/package`;

export const fmtSize = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} КБ` : `${(n / 1024 / 1024).toFixed(1)} МБ`);
