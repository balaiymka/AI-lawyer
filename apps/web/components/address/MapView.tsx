"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useRef } from "react";

import type { Place } from "@/components/address/types";

// Карта OpenStreetMap: точки ЖК, выбранное место, клик по карте → координаты.
export default function MapView({
  center,
  zoom,
  points,
  selected,
  onPointClick,
  onMapClick,
}: {
  center: [number, number];
  zoom: number;
  points: Place[];
  selected: Place | null;
  onPointClick: (p: Place) => void;
  onMapClick: (lat: number, lon: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const handlers = useRef({ onPointClick, onMapClick });
  handlers.current = { onPointClick, onMapClick };

  useEffect(() => {
    if (!box.current || map.current) return;
    const m = L.map(box.current, { zoomControl: true, attributionControl: true }).setView(center, zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) => handlers.current.onMapClick(e.latlng.lat, e.latlng.lng));
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    map.current?.setView(center, zoom);
  }, [center, zoom]);

  useEffect(() => {
    const g = layer.current;
    if (!g) return;
    g.clearLayers();
    const warm = getComputedStyle(document.documentElement).getPropertyValue("--warm").trim() || "#f0a35e";
    for (const p of points) {
      L.circleMarker([p.lat, p.lon], { radius: 6, color: warm, weight: 2, fillColor: warm, fillOpacity: 0.35 })
        .bindTooltip(p.name ?? p.label)
        .on("click", (e) => {
          L.DomEvent.stopPropagation(e);
          handlers.current.onPointClick(p);
        })
        .addTo(g);
    }
    if (selected) {
      L.circleMarker([selected.lat, selected.lon], { radius: 11, color: "#fff", weight: 3, fillColor: warm, fillOpacity: 1 })
        .bindTooltip(selected.label, { permanent: true, direction: "top", offset: [0, -10] })
        .addTo(g);
      map.current?.setView([selected.lat, selected.lon], Math.max(map.current.getZoom(), 15));
    }
  }, [points, selected]);

  return <div ref={box} className="zhkh-map h-full w-full" />;
}
