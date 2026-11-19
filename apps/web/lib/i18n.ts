import kk from "@/messages/kk.json";
import ru from "@/messages/ru.json";

export const locales = ["kk", "ru"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "ru";

export type Dictionary = typeof ru;

const dictionaries: Record<Locale, Dictionary> = { ru, kk };

export function isLocale(value: string): value is Locale {
  return (locales as readonly string[]).includes(value);
}

export function getDictionary(locale: Locale): Dictionary {
  return dictionaries[locale];
}
