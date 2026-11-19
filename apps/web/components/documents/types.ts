export type FieldDef = {
  key: string;
  label: string;
  type: "text" | "textarea" | "date" | "number" | "select";
  required: boolean;
  hint: string;
  options: { value: string; label: string }[];
};

export type TemplateDef = {
  code: string;
  title: string;
  description: string;
  basis: string[];
  category: "osi" | "flood";
  fields: FieldDef[];
};

export type RenderedDoc = {
  title: string;
  to: string[];
  sender: string[];
  body: string[];
  requests_intro: string;
  requests: string[];
  attachments_title: string;
  attachments: string[];
  signature: string[];
  note: string;
};

export function docToText(d: RenderedDoc): string {
  const out: string[] = [];
  if (d.to.length) out.push(d.to.join("\n"), "");
  if (d.sender.length) out.push(d.sender.join("\n"), "");
  out.push(d.title, "", ...d.body);
  if (d.requests.length) out.push("", d.requests_intro, ...d.requests.map((r, i) => `${i + 1}) ${r}`));
  if (d.attachments.length) out.push("", d.attachments_title, ...d.attachments.map((a, i) => `${i + 1}. ${a}`));
  if (d.signature.length) out.push("", ...d.signature);
  return out.join("\n");
}
