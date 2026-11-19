// Клиент чата: POST /v1/chat → поток Server-Sent Events.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Role = "owner" | "osi" | "uk" | "lawyer";

export type Source = {
  chunk_id: string;
  unit_id: string;
  act_code: string;
  act_title: string;
  article: string | null;
  point: string | null;
  path: string;
  lang: string;
  text: string;
  breadcrumb: string;
  version_date: string | null;
  url: string | null;
  valid_to?: string | null;
  is_current?: boolean;
  hierarchy_level?: number | null;
  xref_from?: string | null;
};

export type LegalBasis = {
  chunk_id: string;
  act: string;
  article: string;
  point: string;
  quote: string;
  explanation: string;
  quote_verified: boolean;
};

export type Answer = {
  verdict?: "yes" | "no" | "partly" | "depends";
  verdict_text?: string;
  summary: string;
  legal_answer?: string;
  assumptions: string[];
  legal_basis: LegalBasis[];
  responsibility: { party: string; liability_type: "civil" | "administrative" | "none" | "unclear"; reason: string; citations: string[] }[];
  assessment: { position: "strong" | "moderate" | "weak" | "unclear"; reasoning: string; risks: string[] };
  action_plan: { step: string; who: string; where: string; evidence: string[]; deadline: string; citations: string[] }[];
  documents: string[];
  clarifying_questions: string[];
  not_found: boolean;
  disclaimer: string;
};

export type Edition = { act_code: string; event_date: string; valid_from: string; valid_to: string | null; exact: boolean };

export type Verification = { removed_citations: string[]; replaced_quotes: number; unverified_refs: string[]; needs_review: boolean };

export type ChatEvent =
  | { event: "status"; data: { stage: "normalize" | "search" | "answer" } }
  | { event: "normalized"; data: { reply_lang: "kk" | "ru"; category: string; source: string } }
  | { event: "sources"; data: { sources: Source[] } }
  | { event: "delta"; data: { text: string } }
  | { event: "notice"; data: { code: string } }
  | { event: "answer"; data: { answer: Answer; verification: Verification; mode: "llm" | "demo"; reply_lang: string; event_date?: string; event_date_precision?: string; edition?: Edition | null } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: { case_id: string | null } };

export type ChatRequest = {
  q: string;
  role?: Role;
  case_id?: string | null;
  history?: { role: "user" | "assistant"; text: string }[];
};

export async function streamChat(body: ChatRequest, onEvent: (e: ChatEvent) => void, signal?: AbortSignal) {
  const res = await fetch(`${API_URL}/v1/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let sep: number;
    while ((sep = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      let name = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent({ event: name, data: JSON.parse(data) } as ChatEvent);
    }
  }
}

// Во время потока модель пишет JSON — достаём из него поле summary, чтобы показывать текст сразу.
export function partialSummary(raw: string): string {
  if (!raw.trimStart().startsWith("{")) return raw;
  const m = raw.match(/"summary"\s*:\s*"((?:[^"\\]|\\.)*)/);
  if (!m) return "";
  try {
    return JSON.parse(`"${m[1].replace(/\\$/, "")}"`);
  } catch {
    return m[1];
  }
}
