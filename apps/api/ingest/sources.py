import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SOURCES_FILE = Path(__file__).with_name("sources.toml")


@dataclass(frozen=True)
class ActSource:
    code: str
    act_type: str
    title_ru: str
    adilet_id: str
    hierarchy_level: int
    title_kk: str | None = None
    number: str | None = None
    adopted_at: date | None = None
    enabled: bool = True

    def url(self, lang: str) -> str:
        return f"https://adilet.zan.kz/{'kaz' if lang == 'kk' else 'rus'}/docs/{self.adilet_id}"


def load_sources(path: Path = SOURCES_FILE) -> dict[str, ActSource]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    sources = {}
    for raw in data["acts"]:
        if isinstance(raw.get("adopted_at"), str):
            raw["adopted_at"] = date.fromisoformat(raw["adopted_at"])
        src = ActSource(**raw)
        sources[src.code] = src
    return sources
