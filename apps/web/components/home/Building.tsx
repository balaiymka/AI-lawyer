import { useId } from "react";

// Стеклянный жилой комплекс с горящими окнами и голографическим кольцом (декор, без смысла для скринридеров).
export function Building({ className }: { className?: string }) {
  const u = useId().replace(/:/g, "");
  const id = (n: string) => `${u}-${n}`;
  const url = (n: string) => `url(#${id(n)})`;
  const lit = [[186, 140], [242, 206], [214, 294], [186, 360], [256, 404], [102, 266], [88, 420]];
  return (
    <svg viewBox="0 0 420 560" className={className} aria-hidden="true" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={id("bf")} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3A63E8" /><stop offset="0.5" stopColor="#18307F" /><stop offset="1" stopColor="#0A1235" /></linearGradient>
        <linearGradient id={id("bs")} x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#0E1C55" /><stop offset="1" stopColor="#070D2A" /></linearGradient>
        <linearGradient id={id("bt")} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#BFD7FF" /><stop offset="1" stopColor="#5B7FE8" /></linearGradient>
        <linearGradient id={id("refl")} x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#fff" stopOpacity="0" /><stop offset="0.5" stopColor="#fff" stopOpacity="0.22" /><stop offset="1" stopColor="#fff" stopOpacity="0" /></linearGradient>
        <pattern id={id("win")} width="14" height="22" patternUnits="userSpaceOnUse"><rect x="2" y="3" width="10" height="15" rx="1.5" fill="#9DB8FF" fillOpacity="0.22" /></pattern>
        <pattern id={id("wins")} width="10" height="22" patternUnits="userSpaceOnUse"><rect x="2" y="3" width="6" height="15" rx="1" fill="#7F9BE8" fillOpacity="0.16" /></pattern>
        <radialGradient id={id("gnd")} cx="0.5" cy="0.5" r="0.5"><stop offset="0" stopColor="#5B8CFF" stopOpacity="0.75" /><stop offset="1" stopColor="#2F6BFF" stopOpacity="0" /></radialGradient>
        <filter id={id("glow")} x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4" /></filter>
      </defs>
      <ellipse cx="210" cy="512" rx="200" ry="40" fill={url("gnd")} />
      <polygon points="70,190 150,170 150,505 70,515" fill={url("bf")} />
      <polygon points="150,170 186,184 186,500 150,505" fill={url("bs")} />
      <rect x="74" y="200" width="74" height="300" fill={url("win")} />
      <polygon points="70,190 150,170 186,184 106,204" fill={url("bt")} opacity="0.85" />
      <polygon points="168,52 286,30 286,500 168,510" fill={url("bf")} />
      <polygon points="286,30 340,52 340,492 286,500" fill={url("bs")} />
      <rect x="172" y="66" width="110" height="430" fill={url("win")} />
      <rect x="290" y="60" width="46" height="428" fill={url("wins")} />
      <polygon points="168,52 286,30 340,52 222,74" fill={url("bt")} />
      <rect x="196" y="40" width="30" height="470" fill={url("refl")} />
      <g stroke="#BFD7FF" strokeOpacity="0.35" strokeWidth="1.2">
        {[118, 184, 250, 316, 382, 448].map((y) => <line key={y} x1="168" y1={y} x2="286" y2={y - 14} />)}
      </g>
      <g fill="#FFB86B">{lit.map(([x, y]) => <rect key={`${x}-${y}`} x={x} y={y} width="10" height="15" rx="1.5" />)}</g>
      <g fill="#FFB86B" filter={url("glow")} opacity="0.8" className="windows-glow">{lit.slice(0, 5).map(([x, y]) => <rect key={`${x}-${y}`} x={x} y={y} width="10" height="15" />)}</g>
      <line x1="286" y1="30" x2="286" y2="500" stroke="#E8F0FF" strokeOpacity="0.7" strokeWidth="1.5" />
      <g className="holo-ring">
        <ellipse cx="210" cy="300" rx="196" ry="46" fill="none" stroke="#6E95FF" strokeWidth="1.5" strokeDasharray="3 7" opacity="0.8" />
        <ellipse cx="210" cy="300" rx="196" ry="46" fill="none" stroke="#2F6BFF" strokeWidth="6" opacity="0.25" filter={url("glow")} />
        <circle cx="25" cy="294" r="5" fill="#BFD7FF" />
        <circle cx="398" cy="310" r="4" fill="#B9A8FF" />
      </g>
    </svg>
  );
}
