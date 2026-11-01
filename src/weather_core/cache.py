"""A caching `WeatherProvider` wrapper that also serves recent data when the provider fails.

Open-Meteo rate-limits per IP, and Lambda shares AWS address ranges, so a 429 is a matter of when, not
if. Caching keeps call volume low, and stale-on-error keeps answers flowing when a 429 or an outage
does happen. Entries are stored as JSON strings, so a DynamoDB store can implement `CacheStore` later.
"""

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from pydantic import TypeAdapter

from weather_core.dates import utc_now
from weather_core.errors import RateLimitedError, UpstreamUnavailableError
from weather_core.models import Forecast, Location, Units
from weather_core.provider import WeatherProvider

_locations = TypeAdapter(list[Location])


@dataclass(frozen=True)
class CacheEntry:
    value: str
    stored_at: datetime


class CacheStore(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...
    def set(self, key: str, entry: CacheEntry) -> None: ...


class InMemoryCacheStore:
    """Bounded per-process store; the least recently used entry goes first."""

    def __init__(self, max_entries: int = 1024) -> None:
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_entries = max_entries

    def get(self, key: str) -> CacheEntry | None:
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
        return entry

    def set(self, key: str, entry: CacheEntry) -> None:
        self._entries[key] = entry
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


def geocode_key(query: str, country_code: str | None, count: int, language: str) -> str:
    # Case and spacing only. Diacritics stay significant, so "Wrocław" and "Warsaw" never collide.
    normalized = " ".join(query.split()).casefold()
    return f"geo|{normalized}|{(country_code or '').upper()}|{count}|{language}"


def forecast_key(latitude: float, longitude: float, start_date: date, end_date: date, units: Units) -> str:
    return f"fc|{latitude:.4f}|{longitude:.4f}|{start_date.isoformat()}|{end_date.isoformat()}|{units.value}"


class CachedWeatherProvider:
    """Implements `WeatherProvider` on top of another provider."""

    def __init__(
        self,
        inner: WeatherProvider,
        *,
        store: CacheStore | None = None,
        clock: Callable[[], datetime] = utc_now,
        geocode_ttl: timedelta = timedelta(days=7),
        forecast_ttl: timedelta = timedelta(minutes=30),
        max_stale: timedelta = timedelta(hours=6),
    ) -> None:
        self._inner = inner
        self._store = store if store is not None else InMemoryCacheStore()
        self._clock = clock
        self._geocode_ttl = geocode_ttl
        self._forecast_ttl = forecast_ttl
        self._max_stale = max_stale

    async def search_locations(
        self,
        query: str,
        *,
        country_code: str | None = None,
        count: int = 10,
        language: str = "en",
    ) -> list[Location]:
        key = geocode_key(query, country_code, count, language)
        entry = self._store.get(key)
        if entry is not None and self._age(entry) <= self._geocode_ttl:
            return _locations.validate_json(entry.value)
        try:
            locations = await self._inner.search_locations(
                query, country_code=country_code, count=count, language=language
            )
        except (RateLimitedError, UpstreamUnavailableError):
            # Place coordinates don't change, so any cached copy beats no answer.
            if entry is not None:
                return _locations.validate_json(entry.value)
            raise
        self._store.set(key, CacheEntry(_locations.dump_json(locations).decode(), self._clock()))
        return locations

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        units: Units = Units.METRIC,
    ) -> Forecast:
        key = forecast_key(latitude, longitude, start_date, end_date, units)
        entry = self._store.get(key)
        if entry is not None and self._age(entry) <= self._forecast_ttl:
            return Forecast.model_validate_json(entry.value)
        try:
            forecast = await self._inner.get_forecast(latitude, longitude, start_date, end_date, units)
        except (RateLimitedError, UpstreamUnavailableError):
            if entry is not None and self._age(entry) <= self._forecast_ttl + self._max_stale:
                return Forecast.model_validate_json(entry.value).model_copy(update={"stale": True})
            raise
        self._store.set(key, CacheEntry(forecast.model_dump_json(), self._clock()))
        return forecast

    def _age(self, entry: CacheEntry) -> timedelta:
        return self._clock() - entry.stored_at
