"""Разбор отрендеренной страницы акта с adilet.zan.kz в дерево юридических единиц.

Страница Adilet — SPA. После рендера текст акта лежит плоским списком блоков
`div.law-paragraph` внутри `.law-classic-content`. Иерархию (раздел → глава → параграф →
статья → пункт → подпункт) восстанавливаем по тексту блоков, а не по тегам: в русской версии
статьи размечены `<h3>`, в казахской — `<p><b>NN-бап.</b></p>`.

Путь единицы (`path`) не зависит от языка (`art42/p3/sp1`), поэтому kk и ru версии
сопоставляются по нему.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from bs4 import BeautifulSoup, Tag

Lang = Literal["ru", "kk"]

NUM = r"(\d+(?:-\d+)*)"

HEADING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("section", re.compile(rf"^раздел\s+{NUM}\.?\s*(.*)$", re.I)),
    ("section", re.compile(rf"^{NUM}[\s-]*б[өо]л[iі]м\.?\s*(.*)$", re.I)),
    ("chapter", re.compile(rf"^глава\s+{NUM}\.?\s*(.*)$", re.I)),
    ("chapter", re.compile(rf"^{NUM}[-\s]?тарау\.?\s*(.*)$", re.I)),
    ("paragraph", re.compile(rf"^параграф\s+{NUM}\.?\s*(.*)$", re.I)),
    ("paragraph", re.compile(rf"^{NUM}[-\s]?параграф\.?\s*(.*)$", re.I)),
    ("article", re.compile(rf"^статья\s+{NUM}\.?\s*(.*)$", re.I)),
    ("article", re.compile(rf"^{NUM}[-\s]?бап\.?\s*(.*)$", re.I)),  # встречается «98-2 бап.» без дефиса
]
# Заголовки раздела/главы/параграфа иногда набраны обычным абзацем без <h3>/<b> (напр. «1-тарау. Жалпы
# ережелер» в kk). Для таких блоков требуем точку после номера и пробел (статьи так не распознаём —
# строка текста вида «Статья 5 настоящего Закона…» слишком легко даёт ложное срабатывание).
PLAIN_STRUCT_HEADING_RE = re.compile(
    rf"^(?:(?:глава|параграф)\s+{NUM}|{NUM}[-\s]?(?:тарау|параграф))\.\s+\S", re.I
)
POINT_RE = re.compile(rf"^{NUM}\.\s+\S")
SUBPOINT_RE = re.compile(rf"^{NUM}\)\s+\S")
NOTE_RE = re.compile(r"^(сноска|ескерту)\.", re.I)
# «Приложение 1 к Правилам…» / «Қағидаларға 1-қосымша»: дальше идёт форма со своей нумерацией с 1.
ANNEX_RE = re.compile(r"^приложение\b|^\d*-?қосымша\b|қосымша$", re.I)
# Форма в приложении часто начинается сразу с заголовка капслоком: «АКТ осмотра…», «ПРОТОКОЛ …», «ХАТТАМА …».
FORM_TITLE_RE = re.compile(r"^[А-ЯЁӘҒҚҢӨҰҮҺІ]{3,}(?:\s|$)")
REPEAL_RE = re.compile(r"исключен|утратил[аио]?\s+силу|алып\s+тасталды|күші\s+жойылды", re.I)

LEVEL = {"root": 0, "section": 1, "chapter": 2, "paragraph": 3, "article": 4, "point": 5, "subpoint": 6}


@dataclass
class Node:
    unit_type: str
    number: str | None = None
    heading: str | None = None
    path: str = ""
    anchor: str | None = None
    content: list[str | Node] = field(default_factory=list)  # строки и дочерние узлы по порядку
    notes: list[str] = field(default_factory=list)
    is_repealed: bool = False

    @property
    def children(self) -> list[Node]:
        return [c for c in self.content if isinstance(c, Node)]

    @property
    def own_text(self) -> str:
        return "\n".join(c for c in self.content if isinstance(c, str))

    @property
    def full_text(self) -> str:
        """Текст с вложенными единицами в исходном порядке (для пункта — вместе с подпунктами)."""
        parts: list[str] = []
        for c in self.content:
            if isinstance(c, str):
                parts.append(c)
            elif c.unit_type in ("point", "subpoint"):
                parts.append(c.full_text)
        return "\n".join(p for p in parts if p)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class ParsedAct:
    lang: Lang
    root: Node
    warnings: list[str] = field(default_factory=list)

    def units(self) -> list[Node]:
        return [n for n in self.root.walk() if n.unit_type != "root"]

    def by_path(self) -> dict[str, Node]:
        return {n.path: n for n in self.units()}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _is_heading_block(block: Tag) -> bool:
    if block.find(["h1", "h2", "h3", "h4"]) or block.find(attrs={"data-toc-head": True}):
        return True
    bold = block.find("b")
    return bold is not None and _clean(bold.get_text()) == _clean(block.get_text())


def _is_note_block(block: Tag, text: str) -> bool:
    if block.find(class_="note") is not None:
        return True
    return bool(NOTE_RE.match(text))


def _classify_heading(text: str) -> tuple[str, str, str] | None:
    for unit_type, pattern in HEADING_PATTERNS:
        m = pattern.match(text)
        if m:
            return unit_type, m.group(1), _clean(m.group(2)) or None
    return None


class _Builder:
    def __init__(self, lang: Lang) -> None:
        self.lang = lang
        self.root = Node("root", path="")
        self.stack: list[Node] = [self.root]
        self.seen_paths: set[str] = set()
        self.warnings: list[str] = []
        # Подзаконные акты (приказы с Правилами/Методикой) не делятся на статьи: пункты лежат прямо в главах.
        # Пока не встретилась ни одна статья, разрешаем «свободные» пункты; приложений может быть несколько.
        self.seen_article = False
        self.annex = 1

    # --- стек иерархии -------------------------------------------------
    @property
    def top(self) -> Node:
        return self.stack[-1]

    def _pop_to_level_below(self, level: int) -> None:
        while LEVEL[self.top.unit_type] >= level:
            self.stack.pop()

    def _nearest(self, *types: str) -> Node | None:
        for node in reversed(self.stack):
            if node.unit_type in types:
                return node
        return None

    @property
    def _annex_prefix(self) -> str:
        return f"a{self.annex}/" if self.annex > 1 else ""

    def _make_path(self, unit_type: str, number: str) -> str:
        if unit_type == "section":
            return f"{self._annex_prefix}sec{number}"
        if unit_type == "chapter":
            return f"{self._annex_prefix}ch{number}"
        if unit_type == "paragraph":
            chapter = self._nearest("chapter")
            return f"{chapter.path}/par{number}" if chapter else f"{self._annex_prefix}par{number}"
        if unit_type == "article":
            return f"art{number}"
        parent = self.top
        if unit_type == "point" and parent.unit_type in ("root", "section", "chapter", "paragraph"):
            # Пункт без статьи: до первой главы — текст самого приказа («1. Утвердить Правила…»),
            # дальше — пункты приложения (Правил), у них сквозная нумерация: p15 = «пункт 15 Правил».
            if self._nearest("chapter", "section", "paragraph") is None and self.annex == 1:
                return f"order/p{number}"
            return f"{self._annex_prefix}p{number}"
        prefix = "p" if unit_type == "point" else "sp"
        return f"{parent.path}/{prefix}{number}" if parent.path else f"{prefix}{number}"

    def _push(self, node: Node) -> None:
        self._pop_to_level_below(LEVEL[node.unit_type])
        node.path = self._make_path(node.unit_type, node.number or "")
        if node.path in self.seen_paths:
            # Adilet иногда дублирует заголовок главы (старая и новая редакция подряд).
            existing = self._find(node.path)
            if existing is not None and not existing.children and not existing.own_text:
                self.stack.append(existing)
                return
            # Внутри пункта бывает два списка подпунктов с нумерацией с 1) — это норма, второй получает «~2».
            if node.unit_type != "subpoint":
                self.warnings.append(f"duplicate path {node.path}, renamed")
            suffix = 2
            while f"{node.path}~{suffix}" in self.seen_paths:
                suffix += 1
            node.path = f"{node.path}~{suffix}"
        self.seen_paths.add(node.path)
        self.top.content.append(node)
        self.stack.append(node)

    def _find(self, path: str) -> Node | None:
        return next((n for n in self.root.walk() if n.path == path), None)

    # --- обработка блоков ----------------------------------------------
    def heading(self, unit_type: str, number: str, title: str | None, anchor: str | None) -> None:
        if unit_type == "article":
            self.seen_article = True
        elif unit_type in ("chapter", "section") and not self.seen_article:
            # «Глава 1» повторилась в акте без статей — началось следующее приложение (вторая Методика и т.п.).
            existing = self._find(self._make_path(unit_type, number))
            if existing is not None and (existing.children or existing.own_text):
                self.annex += 1
        node = Node(unit_type, number=number, heading=title, anchor=anchor)
        # «Статья 20. (Исключена Законом РК от …)» / «Статья 5. Утратила силу …»
        if title and (REPEAL_RE.match(title) or (title.startswith("(") and REPEAL_RE.search(title))):
            node.is_repealed = True
        self._push(node)

    def note(self, text: str) -> None:
        target = self._nearest("article", "paragraph", "chapter", "section") or self.root
        target.notes.append(text)
        if REPEAL_RE.search(text) and not target.children and not target.own_text:
            target.is_repealed = True

    def line(self, text: str, anchor: str | None) -> None:
        seen_chapter = any(p.split("/")[-1].startswith("ch") for p in self.seen_paths)
        if not self.seen_article and len(text) < 200 and (
            ANNEX_RE.search(text) or (seen_chapter and FORM_TITLE_RE.match(text))
        ):
            self.annex += 1
            self.stack = [self.root]
            self.root.content.append(text)
            return
        in_article = self._nearest("article") is not None or not self.seen_article
        if in_article and (m := POINT_RE.match(text)):
            self._pop_to_level_below(LEVEL["point"])
            self._push(Node("point", number=m.group(1), anchor=anchor, content=[text]))
            return
        if in_article and (m := SUBPOINT_RE.match(text)):
            self._pop_to_level_below(LEVEL["subpoint"])
            self._push(Node("subpoint", number=m.group(1), anchor=anchor, content=[text]))
            return
        # Ненумерованный абзац: продолжение пункта (в т.ч. после списка подпунктов) или статьи.
        if self.top.unit_type == "subpoint":
            self.stack.pop()
        self.top.content.append(text)


def parse_adilet_html(html: str, lang: Lang) -> ParsedAct:
    soup = BeautifulSoup(html, "lxml")
    blocks = soup.select("div.law-paragraph")
    builder = _Builder(lang)
    if not blocks:
        builder.warnings.append("no div.law-paragraph blocks found — page not rendered?")

    for block in blocks:
        classes = block.get("class") or []
        if "law-izpi-note" in classes:
            continue
        text = _clean(block.get_text(" "))
        if not text or text in ("МАЗМҰНЫ", "ОГЛАВЛЕНИЕ"):
            continue
        anchor = block.get("data-anchor-id")

        heading = _classify_heading(text)
        # Заголовок проверяем раньше сноски: у исключённых статей Adilet размечает заголовок классом note.
        if heading and _is_heading_block(block):
            builder.heading(*heading, anchor=anchor)
            continue
        if _is_note_block(block, text):
            builder.note(text)
            continue
        if heading and heading[0] != "article" and PLAIN_STRUCT_HEADING_RE.match(text):
            builder.heading(*heading, anchor=anchor)
            continue
        builder.line(text, anchor)

    return ParsedAct(lang=lang, root=builder.root, warnings=builder.warnings)


# --- сопоставление kk / ru ------------------------------------------------

@dataclass
class MergedUnit:
    path: str
    parent_path: str | None
    unit_type: str
    number: str | None
    ord: int
    heading_ru: str | None = None
    heading_kk: str | None = None
    text_ru: str | None = None
    text_kk: str | None = None
    notes_ru: str | None = None
    notes_kk: str | None = None
    anchor: str | None = None
    is_repealed: bool = False


def _unit_text(node: Node) -> str | None:
    # Пункт хранится вместе с подпунктами (единица чанка для RAG); остальные — только свой текст.
    text = node.full_text if node.unit_type == "point" else node.own_text
    return text or None


def merge_languages(ru: ParsedAct, kk: ParsedAct | None) -> tuple[list[MergedUnit], list[str]]:
    """Объединяет русскую и казахскую версии по `path`. Основа порядка — русская версия."""
    warnings: list[str] = []
    kk_map = kk.by_path() if kk else {}
    merged: list[MergedUnit] = []

    def visit(node: Node, parent: Node | None) -> None:
        if node.unit_type != "root":
            k = kk_map.pop(node.path, None)
            merged.append(
                MergedUnit(
                    path=node.path,
                    parent_path=parent.path if parent and parent.unit_type != "root" else None,
                    unit_type=node.unit_type,
                    number=node.number,
                    ord=len(merged),
                    heading_ru=node.heading,
                    heading_kk=k.heading if k else None,
                    text_ru=_unit_text(node),
                    text_kk=_unit_text(k) if k else None,
                    notes_ru="\n".join(node.notes) or None,
                    notes_kk=("\n".join(k.notes) or None) if k else None,
                    anchor=node.anchor,
                    is_repealed=node.is_repealed,
                )
            )
        for child in node.children:
            visit(child, node)

    visit(ru.root, None)
    if kk is not None:
        for path in kk_map:
            warnings.append(f"kk-only unit {path} (нет в русской версии)")
        ru_paths = {u.path for u in merged}
        missing_kk = [p for p in ru_paths if p not in kk.by_path()]
        if missing_kk:
            warnings.append(f"{len(missing_kk)} units without kk text, e.g. {sorted(missing_kk)[:5]}")
    return merged, warnings
