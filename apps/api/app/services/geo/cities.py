"""Города Казахстана для выбора адреса: центр карты и рамка поиска.

Список — города республиканского значения, областные центры и крупные города. Любой другой населённый пункт
находится через поиск («Другой город»).
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class City:
    id: str
    ru: str
    kk: str
    lat: float
    lon: float
    radius: float = 0.25  # полуразмер рамки поиска, градусы широты

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """minLon, minLat, maxLon, maxLat — формат Photon."""
        dlon = self.radius * 1.5
        return (self.lon - dlon, self.lat - self.radius, self.lon + dlon, self.lat + self.radius)

    def public(self) -> dict:
        return {**asdict(self), "bbox": self.bbox}


CITIES: list[City] = [
    City("astana", "Астана", "Астана", 51.1694, 71.4491, 0.3),
    City("almaty", "Алматы", "Алматы", 43.2389, 76.8897, 0.3),
    City("shymkent", "Шымкент", "Шымкент", 42.3417, 69.5901, 0.25),
    City("aktobe", "Актобе", "Ақтөбе", 50.2839, 57.1670),
    City("karaganda", "Караганда", "Қарағанды", 49.8047, 73.1094),
    City("taraz", "Тараз", "Тараз", 42.9000, 71.3667),
    City("pavlodar", "Павлодар", "Павлодар", 52.2873, 76.9674),
    City("oskemen", "Усть-Каменогорск", "Өскемен", 49.9483, 82.6286),
    City("semey", "Семей", "Семей", 50.4111, 80.2275),
    City("atyrau", "Атырау", "Атырау", 47.1167, 51.8833),
    City("kostanay", "Костанай", "Қостанай", 53.2144, 63.6246),
    City("kyzylorda", "Кызылорда", "Қызылорда", 44.8528, 65.5092),
    City("oral", "Уральск", "Орал", 51.2333, 51.3667),
    City("petropavl", "Петропавловск", "Петропавл", 54.8667, 69.1500),
    City("aktau", "Актау", "Ақтау", 43.6500, 51.1500),
    City("turkistan", "Туркестан", "Түркістан", 43.2973, 68.2517),
    City("kokshetau", "Кокшетау", "Көкшетау", 53.2833, 69.3833),
    City("taldykorgan", "Талдыкорган", "Талдықорған", 45.0167, 78.3667),
    City("konaev", "Конаев", "Қонаев", 43.8667, 77.0667, 0.15),
    City("zhezkazgan", "Жезказган", "Жезқазған", 47.7833, 67.7667, 0.15),
    City("ekibastuz", "Экибастуз", "Екібастұз", 51.7231, 75.3228, 0.15),
    City("temirtau", "Темиртау", "Теміртау", 50.0547, 72.9644, 0.15),
    City("rudny", "Рудный", "Рудный", 52.9667, 63.1167, 0.15),
    City("balkhash", "Балхаш", "Балқаш", 46.8481, 74.9950, 0.15),
    City("zhanaozen", "Жанаозен", "Жаңаөзен", 43.3412, 52.8619, 0.15),
]

BY_ID = {c.id: c for c in CITIES}
