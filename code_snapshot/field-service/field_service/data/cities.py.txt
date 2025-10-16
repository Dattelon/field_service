"""Canonical city registry for Field Service (v1.2)."""

from __future__ import annotations

import re
from typing import List

# Ordered canonical list, frozen by product decision (78 entries)
ALLOWED_CITIES: tuple[str, ...] = (
    "",
    "-",
    "",
    "",
    "",
    " ",
    "",
    "",
    "",
    "",
    "  ",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    " ",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    " ()",
    "",
    "",
    "",
    "",
    " ",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    " ()",
    "",
    "",
    "",
    "",
    " ",
    " ",
    " ",
    "",
    "",
    " ",
    "",
    "",
    "",
    "",
    " ()",
    "",
    "",
    "",
)

CITY_TIMEZONES: dict[str, str] = {
    "": "Europe/Moscow",
    "-": "Europe/Moscow",
    "": "Asia/Novosibirsk",
    "": "Asia/Yekaterinburg",
    "": "Europe/Moscow",
    " ": "Europe/Moscow",
    "": "Asia/Yekaterinburg",
    "": "Asia/Krasnoyarsk",
    "": "Europe/Samara",
    "": "Asia/Yekaterinburg",
    "  ": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Asia/Omsk",
    "": "Europe/Moscow",
    "": "Asia/Yekaterinburg",
    "": "Europe/Volgograd",
    "": "Europe/Saratov",
    "": "Asia/Yekaterinburg",
    "": "Europe/Samara",
    "": "Europe/Samara",
    "": "Asia/Barnaul",
    "": "Europe/Ulyanovsk",
    "": "Asia/Irkutsk",
    "": "Asia/Vladivostok",
    "": "Asia/Vladivostok",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Asia/Tomsk",
    "": "Asia/Yekaterinburg",
    "": "Asia/Novokuznetsk",
    "": "Asia/Novokuznetsk",
    "": "Europe/Moscow",
    " ": "Europe/Moscow",
    "": "Europe/Astrakhan",
    "": "Europe/Moscow",
    "": "Europe/Kirov",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Europe/Kaliningrad",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    " ()": "Europe/Moscow",
    "": "Europe/Simferopol",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Asia/Yekaterinburg",
    " ": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Asia/Yekaterinburg",
    "": "Europe/Moscow",
    "": "Asia/Chita",
    "": "Europe/Simferopol",
    "": "Europe/Volgograd",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Asia/Yekaterinburg",
    "": "Europe/Moscow",
    " ()": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Asia/Yakutsk",
    "": "Europe/Moscow",
    " ": "Europe/Moscow",
    " ": "Asia/Irkutsk",
    " ": "Asia/Yekaterinburg",
    "": "Asia/Yekaterinburg",
    "": "Europe/Moscow",
    " ": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    "": "Europe/Moscow",
    " ()": "Europe/Moscow",
    "": "Asia/Yekaterinburg",
    "": "Europe/Saratov",
    "": "Europe/Moscow",
}

_ALIAS_RAW = {
    "": "-",
    "-": "-",
    "": "-",
    "": "",
    "--": "  ",
    "": " ()",
    "": " ()",
    "": " ()",
}

_normalized_lookup = {}
_normalized_names = {}


def _normalize(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.replace("", "")
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
        city for city, normalized in _normalized_names.items()
        if normalized_query in normalized
    ]
    # Sort search results alphabetically
    return sorted(matches)


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
