"""Canonical city registry for Field Service (v1.2)."""

from __future__ import annotations

import re
from typing import List

# Ordered canonical list, frozen by product decision (78 entries)
ALLOWED_CITIES: tuple[str, ...] = (
    "Москва",
    "Санкт Петербург",
    "Новосибирск",
    "Екатеринбург",
    "Казань",
    "Нижний Новгород",
    "Челябинск",
    "Красноярск",
    "Самара",
    "Уфа",
    "Ростов на Дону",
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
    "Балашиха (МО)",
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
    "Подольск (МО)",
    "Архангельск",
    "Грозный",
    "Якутск",
    "Тверь",
    "Старый Оскол",
    "Улан Удэ",
    "Нижний Тагил",
    "Нижневартовск",
    "Псков",
    "Йошкар Ола",
    "Кострома",
    "Новороссийск",
    "Дзержинск",
    "Таганрог",
    "Химки (МО)",
    "Березники",
    "Энгельс",
    "Шахты",
)

CITY_TIMEZONES: dict[str, str] = {
    "Москва": "Europe/Moscow",
    "Санкт Петербург": "Europe/Moscow",
    "Новосибирск": "Asia/Novosibirsk",
    "Екатеринбург": "Asia/Yekaterinburg",
    "Казань": "Europe/Moscow",
    "Нижний Новгород": "Europe/Moscow",
    "Челябинск": "Asia/Yekaterinburg",
    "Красноярск": "Asia/Krasnoyarsk",
    "Самара": "Europe/Samara",
    "Уфа": "Asia/Yekaterinburg",
    "Ростов на Дону": "Europe/Moscow",
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
    "Балашиха (МО)": "Europe/Moscow",
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
    "Подольск (МО)": "Europe/Moscow",
    "Архангельск": "Europe/Moscow",
    "Грозный": "Europe/Moscow",
    "Якутск": "Asia/Yakutsk",
    "Тверь": "Europe/Moscow",
    "Старый Оскол": "Europe/Moscow",
    "Улан Удэ": "Asia/Irkutsk",
    "Нижний Тагил": "Asia/Yekaterinburg",
    "Нижневартовск": "Asia/Yekaterinburg",
    "Псков": "Europe/Moscow",
    "Йошкар Ола": "Europe/Moscow",
    "Кострома": "Europe/Moscow",
    "Новороссийск": "Europe/Moscow",
    "Дзержинск": "Europe/Moscow",
    "Таганрог": "Europe/Moscow",
    "Химки (МО)": "Europe/Moscow",
    "Березники": "Asia/Yekaterinburg",
    "Энгельс": "Europe/Saratov",
    "Шахты": "Europe/Moscow",
}

_ALIAS_RAW = {
    "спб": "Санкт Петербург",
    "санкт-петербург": "Санкт Петербург",
    "питер": "Санкт Петербург",
    "екб": "Екатеринбург",
    "ростов-на-дону": "Ростов на Дону",
    "балашиха": "Балашиха (МО)",
    "подольск": "Подольск (МО)",
    "химки": "Химки (МО)",
}

_normalized_lookup = {}
_normalized_names = {}


def _normalize(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.replace("ё", "е")
    lowered = re.sub(r"[\u2010-\u2015]", "-", lowered)
    lowered = lowered.replace("-", " ")
    lowered = lowered.replace("(", " ").replace(")", " ")
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


for _city in ALLOWED_CITIES:
    normalized = _normalize(_city)
    _normalized_names[_city] = normalized
    _normalized_lookup[normalized] = _city

CITY_ALIASES = { _normalize(key): value for key, value in _ALIAS_RAW.items() }


def all_cities() -> List[str]:
    return list(ALLOWED_CITIES)


def is_allowed_city(name: str) -> bool:
    return name in _normalized_names


def resolve_city_name(value: str) -> str | None:
    normalized = _normalize(value)
    if not normalized:
        return None
    if normalized in CITY_ALIASES:
        return CITY_ALIASES[normalized]
    return _normalized_lookup.get(normalized)


def match_cities(query: str | None) -> List[str]:
    if query is None or not query.strip():
        return list(ALLOWED_CITIES)
    resolved = resolve_city_name(query)
    if resolved:
        return [resolved]
    normalized_query = _normalize(query)
    if not normalized_query:
        return list(ALLOWED_CITIES)
    matches = [
        city for city, normalized in _normalized_names.items()
        if normalized_query in normalized
    ]
    return matches


def get_timezone(city_name: str) -> str | None:
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
