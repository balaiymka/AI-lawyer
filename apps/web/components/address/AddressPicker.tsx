"use client";

import { clsx } from "clsx";
import { Building, Building2, Check, Loader2, MapPin, Navigation, PencilLine, Search, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import type { City, Picked, Place } from "@/components/address/types";
import { apiGet } from "@/lib/api";
import type { Dictionary, Locale } from "@/lib/i18n";

const MapView = dynamic(() => import("@/components/address/MapView"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-surface-2" />,
});

const CITY_KEY = "zhkh24-city";
const OTHER = "__other";
const KZ_CENTER: [number, number] = [48.0, 67.0];

const KIND_ICON = { complex: Building2, building: Building, street: Navigation, city: MapPin, other: MapPin } as const;

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function AddressPicker({ t, locale, onPick, onClose }: { t: Dictionary; locale: Locale; onPick: (p: Picked) => void; onClose: () => void }) {
  const a = t.addr;
  const [cities, setCities] = useState<City[]>([]);
  const [cityId, setCityId] = useState<string>(() => {
    try {
      return localStorage.getItem(CITY_KEY) || "almaty";
    } catch {
      return "almaty";
    }
  });
  const [tab, setTab] = useState<"search" | "complex">("search");
  const [q, setQ] = useState("");
  const [complexQ, setComplexQ] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [complexes, setComplexes] = useState<Place[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState<Place | null>(null);
  const dq = useDebounced(q.trim(), 450);

  const city = cities.find((c) => c.id === cityId) ?? null;
  const cityName = city ? (locale === "kk" ? city.kk : city.ru) : null;

  useEffect(() => {
    apiGet<City[]>("/v1/geo/cities").then(setCities).catch(() => setError(true));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  useEffect(() => {
    try {
      localStorage.setItem(CITY_KEY, cityId);
    } catch {}
    setComplexes(null);
    setResults(null);
    setSelected(null);
  }, [cityId]);

  // Поиск адреса
  useEffect(() => {
    if (dq.length < 2) return setResults(null);
    const cityParam = cityId === OTHER ? "" : `&city=${cityId}`;
    setLoading(true);
    apiGet<Place[]>(`/v1/geo/search?q=${encodeURIComponent(dq)}${cityParam}`)
      .then((r) => {
        setResults(r);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [dq, cityId]);

  // ЖК города
  useEffect(() => {
    if (tab !== "complex" || cityId === OTHER || complexes) return;
    setLoading(true);
    apiGet<Place[]>(`/v1/geo/complexes?city=${cityId}`)
      .then((r) => {
        setComplexes(r);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [tab, cityId, complexes]);

  const shownComplexes = useMemo(() => {
    const s = complexQ.trim().toLowerCase();
    return (complexes ?? []).filter((c) => !s || (c.name ?? c.label).toLowerCase().includes(s));
  }, [complexes, complexQ]);

  const list = tab === "search" ? results : shownComplexes;
  const center: [number, number] = city ? [city.lat, city.lon] : KZ_CENTER;
  const zoom = city ? 12 : 5;

  async function pickPoint(lat: number, lon: number) {
    setLoading(true);
    try {
      const p = await apiGet<Place | null>(`/v1/geo/reverse?lat=${lat}&lon=${lon}`);
      if (p) setSelected(p);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  function confirm() {
    if (!selected) return;
    onPick({ label: selected.label, city: selected.city ?? cityName, place: selected });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 backdrop-blur-sm sm:items-center sm:p-6" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={a.title} onClick={(e) => e.stopPropagation()}
        className="flex h-[92dvh] w-full max-w-5xl flex-col overflow-hidden rounded-t-[28px] border border-line bg-bg shadow-2xl sm:h-[82dvh] sm:rounded-[28px]">
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <MapPin className="size-5 text-warm" />
          <h2 className="font-semibold">{a.title}</h2>
          <select value={cityId} onChange={(e) => setCityId(e.target.value)} aria-label={a.city}
            className="ml-auto max-w-[45%] rounded-full border border-line bg-surface-2 px-3 py-1.5 text-sm outline-none">
            {cities.map((c) => <option key={c.id} value={c.id}>{locale === "kk" ? c.kk : c.ru}</option>)}
            <option value={OTHER}>{a.otherCity}</option>
          </select>
          <button type="button" onClick={onClose} aria-label="×" className="grid size-9 place-items-center rounded-full hover:bg-surface-2">
            <X className="size-5" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 grid-rows-[38%_1fr] md:grid-cols-[380px_1fr] md:grid-rows-1">
          <div className="relative order-1 md:order-2">
            <MapView center={center} zoom={zoom} points={tab === "complex" ? shownComplexes : results?.filter((r) => r.kind !== "city") ?? []}
              selected={selected} onPointClick={setSelected} onMapClick={pickPoint} />
            <p className="pointer-events-none absolute left-3 top-3 z-[400] rounded-full bg-bg/85 px-3 py-1 text-xs shadow">{a.mapHint}</p>
          </div>

          <div className="order-2 flex min-h-0 flex-col border-line md:order-1 md:border-r">
            <div role="tablist" className="flex gap-1 p-3 pb-0">
              {(["search", "complex"] as const).map((k) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} disabled={k === "complex" && cityId === OTHER}
                  className={clsx("flex-1 rounded-full px-3 py-2 text-sm font-medium transition disabled:opacity-40",
                    tab === k ? "bg-accent text-accent-fg" : "text-muted hover:bg-surface-2")}>
                  {k === "search" ? a.tabSearch : a.tabComplex}
                </button>
              ))}
            </div>
            <div className="relative p-3">
              <Search className="absolute left-6 top-1/2 size-4 -translate-y-1/2 text-muted" />
              {tab === "search" ? (
                <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={a.searchPh}
                  className="w-full rounded-full border border-line bg-surface-2 py-2.5 pl-10 pr-10 text-sm outline-none focus:border-warm/60" />
              ) : (
                <input value={complexQ} onChange={(e) => setComplexQ(e.target.value)} placeholder={a.complexPh}
                  className="w-full rounded-full border border-line bg-surface-2 py-2.5 pl-10 pr-10 text-sm outline-none focus:border-warm/60" />
              )}
              {loading && <Loader2 className="absolute right-6 top-1/2 size-4 -translate-y-1/2 animate-spin text-warm" />}
            </div>

            <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 pb-3">
              {error && <li className="rounded-2xl bg-danger/10 p-3 text-sm text-danger">{a.error}</li>}
              {!error && list && list.length === 0 && (
                <li className="p-3 text-sm text-muted">{tab === "search" ? a.empty : a.complexEmpty}</li>
              )}
              {list?.map((p) => {
                const Icon = KIND_ICON[p.kind];
                const active = selected?.label === p.label;
                return (
                  <li key={`${p.label}-${p.lat}`}>
                    <button type="button" onClick={() => setSelected(p)}
                      className={clsx("flex w-full items-start gap-3 rounded-2xl p-2.5 text-left transition", active ? "bg-warm/15" : "hover:bg-surface-2")}>
                      <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-surface-2"><Icon className="size-4 text-warm" /></span>
                      <span className="min-w-0">
                        <span className="block text-sm font-medium leading-snug">{tab === "complex" ? p.name : p.label}</span>
                        <span className="block text-xs text-muted">
                          {a.kinds[p.kind]}{tab === "complex" && p.street ? ` · ${p.street}${p.housenumber ? `, ${p.housenumber}` : ""}` : ""}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-3">
          <div className="min-w-0 flex-1 text-sm">
            {selected ? (
              <>
                <span className="text-muted">{a.selected}: </span>
                <span className="font-medium">{selected.label}</span>
                {selected.kind !== "building" && <span className="block text-xs text-warning">{a.addHouse}</span>}
              </>
            ) : (
              <span className="text-xs text-muted">{a.source}</span>
            )}
          </div>
          <button type="button" onClick={onClose} className="flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm hover:bg-surface-2">
            <PencilLine className="size-4" />
            {a.manual}
          </button>
          <button type="button" onClick={confirm} disabled={!selected}
            className="flex items-center gap-2 rounded-full bg-accent px-5 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40">
            <Check className="size-4" />
            {a.choose}
          </button>
        </div>
      </div>
    </div>
  );
}
