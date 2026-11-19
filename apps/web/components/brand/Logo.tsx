import { useId } from "react";

// Знак «ЖКХ AI ЮРИСТ»: щит (защита прав) + весы (закон) + янтарная точка (интеллект).
export function LogoMark({ size = 40 }: { size?: number }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="6" y1="4" x2="42" y2="44">
          <stop offset="0" stopColor="#BFD7FF" />
          <stop offset="0.55" stopColor="#2F6BFF" />
          <stop offset="1" stopColor="#B9A8FF" />
        </linearGradient>
      </defs>
      <path d="M24 3.5 41 10v13.2c0 10.2-7 18.6-17 21.3C14 41.8 7 33.4 7 23.2V10L24 3.5Z" stroke={`url(#${id})`} strokeWidth="2.4" fill="rgba(47,107,255,0.14)" />
      <path d="M15 22h18M24 15v19M17.5 22l-3 7h6l-3-7ZM30.5 22l-3 7h6l-3-7Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="24" cy="15" r="2.6" fill="#FFB86B" />
    </svg>
  );
}
