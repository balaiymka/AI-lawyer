import { API_URL } from "@/lib/chat";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

// «art42/p17» → «ст. 42 п. 17» / «42-бап 17-тармақ»
export function refLabel(path: string, locale: string): string {
  const m = path.match(/^art([\d-]+)(?:\/p(\d+))?/);
  if (!m) return path;
  const [, a, p] = m;
  return locale === "kk" ? `${a}-бап${p ? ` ${p}-тармақ` : ""}` : `ст. ${a}${p ? ` п. ${p}` : ""}`;
}

// Форматирование без Intl: данные локалей на сервере (Node) и в браузере различаются,
// из-за этого «32 000» на сервере превращалось в «32,000» в браузере и ломало гидратацию.
const KK_MONTHS = ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"];
const RU_MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"];
const pad = (n: number) => String(n).padStart(2, "0");

export const fmtNumber = (n: number) => {
  const [int, frac] = (Math.round(n * 100) / 100).toFixed(2).split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  return frac === "00" ? grouped : `${grouped},${frac.replace(/0$/, "")}`;
};

export const fmtDate = (d: Date | number | string, withTime = false) => {
  const x = new Date(d);
  const utc = typeof d === "number";
  const [day, mon, yr] = utc ? [x.getUTCDate(), x.getUTCMonth(), x.getUTCFullYear()] : [x.getDate(), x.getMonth(), x.getFullYear()];
  const date = `${pad(day)}.${pad(mon + 1)}.${yr}`;
  return withTime ? `${date}, ${pad(x.getHours())}:${pad(x.getMinutes())}` : date;
};

export const fmtMonth = (y: number, m: number, locale: string) =>
  locale === "kk" ? `${y} ж. ${KK_MONTHS[m]}` : `${RU_MONTHS[m]} ${y}`;
