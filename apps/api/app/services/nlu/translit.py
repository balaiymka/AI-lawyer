"""Латиница → кириллица для запросов вида «kvorum sobraniya OSI» или «korshi su basty».

Цель — не идеальная транслитерация, а получить кириллическую форму, по которой найдут
лексический поиск и словарь сленга. Казахские буквы восстанавливает уже модель (BGE-M3 к ним устойчива).
"""

from __future__ import annotations

import re

DIGRAPHS = [
    ("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("kh", "х"), ("ch", "ч"), ("sh", "ш"),
    ("ya", "я"), ("ia", "я"), ("yu", "ю"), ("iu", "ю"), ("yo", "ё"), ("ts", "ц"),
]
SINGLE = {
    "a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "e": "е", "z": "з", "i": "и", "j": "ж", "k": "к",
    "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
    "f": "ф", "h": "х", "x": "х", "c": "ц", "w": "у", "'": "ь",
}
VOWELS = set("аеёиоуыэюя")
LATIN = re.compile(r"[a-z]", re.I)
CYR = re.compile(r"[а-яёәғқңөұүһі]", re.I)


def is_mostly_latin(text: str) -> bool:
    lat, cyr = len(LATIN.findall(text)), len(CYR.findall(text))
    return lat > 0 and lat >= 2 * cyr


def _word(w: str) -> str:
    out: list[str] = []
    i = 0
    lw = w.lower()
    while i < len(lw):
        for src, dst in DIGRAPHS:
            if lw.startswith(src, i):
                out.append(dst)
                i += len(src)
                break
        else:
            ch = lw[i]
            prev_vowel = bool(out) and out[-1] in VOWELS
            if ch == "y":
                out.append("й" if prev_vowel else "ы")
            elif ch == "i" and prev_vowel and (i + 1 == len(lw) or lw[i + 1] not in "aeiouy"):
                out.append("й")  # bermei → бермей
            else:
                out.append(SINGLE.get(ch, ch))
            i += 1
    return "".join(out)


def latin_to_cyrillic(text: str) -> str:
    return re.sub(r"[A-Za-z']+", lambda m: _word(m.group(0)), text)
