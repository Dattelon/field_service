"""Canonical city registry for Field Service (v1.2)."""

from __future__ import annotations

import re
from typing import List

# Ordered canonical list, frozen by product decision (79 entries)
ALLOWED_CITIES: tuple[str, ...] = (
    "Москва",
    "Санкт-Петербург",
    "Новосибирск",
    "Екатеринбург",
    "Казань",
    "Нижний Новгород",
    "Челябинск",
    "Красноярск",
    "Самара",
    "Уфа",
    "Ростов-на-Дону",
    "Краснодар",
    "Омск",
    "Воронеж",
    "Пермь",
    "Волгоград",
    "Саратов",
    "Тюмень",
    "Тольятти",
    "Ижевск",
    "Барнаул",
    "Ульяновск",
    "Иркутск",
    "Хабаровск",
    "Владивосток",
    "Ярославль",
    "Махачкала",
    "Томск",
    "Оренбург",
    "Кемерово",
    "Новокузнецк",
    "Рязань",
    "Набережные Челны",
    "Астрахань",
    "Пенза",
    "Киров",
    "Липецк",
    "Чебоксары",
    "Калининград",
    "Тула",
    "Курск",
    "Сочи",
    "Ставрополь",
    "Балашиха",
    "Севастополь",
    "Брянск",
    "Белгород",
    "Магнитогорск",
    "Великий Новгород",
    "Калуга",
    "Сургут",
    "Владикавказ",
    "Чита",
    "Симферополь",
    "Волжский",
    "Смоленск",
    "Саранск",
    "Курган",
    "Орёл",
    "Подольск",
    "Архангельск",
    "Грозный",
    "Якутск",
    "Тверь",
    "Старый Оскол",
    "Улан-Удэ",
    "Нижний Тагил",
    "Нижневартовск",
    "Псков",
    "Йошкар-Ола",
    "Кострома",
    "Новороссийск",
    "Дзержинск",
    "Таганрог",
    "Химки",
    "Березники",
    "Энгельс",
    "Шахты",
)

CITY_TIMEZONES: dict[str, str] = {
    "Москва": "Europe/Moscow",
    "Санкт-Петербург": "Europe/Moscow",
    "Новосибирск": "Asia/Novosibirsk",
    "Екатеринбург": "Asia/Yekaterinburg",
    "Казань": "Europe/Moscow",
    "Нижний Новгород": "Europe/Moscow",
    "Челябинск": "Asia/Yekaterinburg",
    "Красноярск": "Asia/Krasnoyarsk",
    "Самара": "Europe/Samara",
    "Уфа": "Asia/Yekaterinburg",
    "Ростов-на-Дону": "Europe/Moscow",
    "Краснодар": "Europe/Moscow",
    "Омск": "Asia/Omsk",
    "Воронеж": "Europe/Moscow",
    "Пермь": "Asia/Yekaterinburg",
    "Волгоград": "Europe/Volgograd",
    "Саратов": "Europe/Saratov",
    "Тюмень": "Asia/Yekaterinburg",
    "Тольятти": "Europe/Samara",
    "Ижевск": "Europe/Samara",
    "Барнаул": "Asia/Barnaul",
    "Ульяновск": "Europe/Ulyanovsk",
    "Иркутск": "Asia/Irkutsk",
    "Хабаровск": "Asia/Vladivostok",
    "Владивосток": "Asia/Vladivostok",
    "Ярославль": "Europe/Moscow",
    "Махачкала": "Europe/Moscow",
    "Томск": "Asia/Tomsk",
    "Оренбург": "Asia/Yekaterinburg",
    "Кемерово": "Asia/Novokuznetsk",
    "Новокузнецк": "Asia/Novokuznetsk",
    "Рязань": "Europe/Moscow",
    "Набережные Челны": "Europe/Moscow",
    "Астрахань": "Europe/Astrakhan",
    "Пенза": "Europe/Moscow",
    "Киров": "Europe/Kirov",
    "Липецк": "Europe/Moscow",
    "Чебоксары": "Europe/Moscow",
    "Калининград": "Europe/Kaliningrad",
    "Тула": "Europe/Moscow",
    "Курск": "Europe/Moscow",
    "Сочи": "Europe/Moscow",
    "Ставрополь": "Europe/Moscow",
    "Балашиха": "Europe/Moscow",
    "Севастополь": "Europe/Simferopol",
    "Брянск": "Europe/Moscow",
    "Белгород": "Europe/Moscow",
    "Магнитогорск": "Asia/Yekaterinburg",
    "Великий Новгород": "Europe/Moscow",
    "Калуга": "Europe/Moscow",
    "Сургут": "Asia/Yekaterinburg",
    "Владикавказ": "Europe/Moscow",
    "Чита": "Asia/Chita",
    "Симферополь": "Europe/Simferopol",
    "Волжский": "Europe/Volgograd",
    "Смоленск": "Europe/Moscow",
    "Саранск": "Europe/Moscow",
    "Курган": "Asia/Yekaterinburg",
    "Орёл": "Europe/Moscow",
    "Подольск": "Europe/Moscow",
    "Архангельск": "Europe/Moscow",
    "Грозный": "Europe/Moscow",
    "Якутск": "Asia/Yakutsk",
    "Тверь": "Europe/Moscow",
    "Старый Оскол": "Europe/Moscow",
    "Улан-Удэ": "Asia/Irkutsk",
    "Нижний Тагил": "Asia/Yekaterinburg",
    "Нижневартовск": "Asia/Yekaterinburg",
    "Псков": "Europe/Moscow",
    "Йошкар-Ола": "Europe/Moscow",
    "Кострома": "Europe/Moscow",
    "Новороссийск": "Europe/Moscow",
    "Дзержинск": "Europe/Moscow",
    "Таганрог": "Europe/Moscow",
    "Химки": "Europe/Moscow",
    "Березники": "Asia/Yekaterinburg",
    "Энгельс": "Europe/Saratov",
    "Шахты": "Europe/Moscow",
}

_ALIAS_RAW = {
    "Питер": "Санкт-Петербург",
    "СПб": "Санкт-Петербург",
    "Петербург": "Санкт-Петербург",
    "Екб": "Екатеринбург",
    "Ростов-на-Дону": "Ростов-на-Дону",
    "Набережные Челны": "Набережные Челны",
    "Нижний Новгород": "Нижний Новгород",
    "Балашиха (МО)": "Балашиха",
}

_normalized_lookup = {}
_normalized_names = {}


def _normalize(value: str) -> str:
    """Normalize city name for matching."""
    lowered = value.strip().lower()
    # Remove ё -> е
    lowered = lowered.replace("ё", "е")
    # Normalize different types of dashes to regular hyphen
    lowered = re.sub(r"[\u2010-\u2015]", "-", lowered)
    lowered = lowered.replace("-", " ")
    lowered = lowered.replace("(", " ").replace(")", " ")
    # Collapse multiple spaces
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


for _city in ALLOWED_CITIES:
    normalized = _normalize(_city)
    _normalized_names[_city] = normalized
    _normalized_lookup[normalized] = _city

CITY_ALIASES = {_normalize(key): value for key, value in _ALIAS_RAW.items()}


def all_cities() -> List[str]:
    """Return all allowed cities."""
    return list(ALLOWED_CITIES)


def is_allowed_city(name: str) -> bool:
    """Check if the city name is in the allowed list."""
    return name in _normalized_names


def resolve_city_name(value: str) -> str | None:
    """Resolve city name from query, including aliases."""
    normalized = _normalize(value)
    if not normalized:
        return None
    if normalized in CITY_ALIASES:
        return CITY_ALIASES[normalized]
    return _normalized_lookup.get(normalized)


def match_cities(query: str | None) -> List[str]:
    """Match cities by query and return them in alphabetical order."""
    if query is None or not query.strip():
        # Return all cities sorted alphabetically
        return sorted(list(ALLOWED_CITIES))
    resolved = resolve_city_name(query)
    if resolved:
        return [resolved]
    normalized_query = _normalize(query)
    if not normalized_query:
        # Return all cities sorted alphabetically
        return sorted(list(ALLOWED_CITIES))
    matches = [
        city
        for city, normalized in _normalized_names.items()
        if normalized_query in normalized
    ]
    # Sort search results alphabetically
    return sorted(matches)


def get_timezone(city_name: str) -> str | None:
    """Get timezone for a city."""
    return CITY_TIMEZONES.get(city_name)


__all__ = [
    "ALLOWED_CITIES",
    "CITY_TIMEZONES",
    "CITY_ALIASES",
    "all_cities",
    "is_allowed_city",
    "resolve_city_name",
    "match_cities",
    "get_timezone",
]
