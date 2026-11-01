from datetime import date, timedelta

import httpx2
import pytest
import time_machine

from tests.support.fakes import FIXTURE_DAY, RecordingSleep
from tests.support.mock_http import MockHTTP, json_reply
from weather_core.cache import CachedWeatherProvider, CacheEntry, InMemoryCacheStore, geocode_key
from weather_core.errors import InvalidRequestError, RateLimitedError, UpstreamUnavailableError
from weather_core.open_meteo import FORECAST_URL, GEOCODING_URL, OpenMeteoProvider

pytestmark = [pytest.mark.unit, pytest.mark.anyio]

NOW = FIXTURE_DAY
WARSAW = (52.2298, 21.0118)
NOV_1, NOV_3 = date(2026, 11, 1), date(2026, 11, 3)


def cached(mock_http: MockHTTP, sleep: RecordingSleep) -> CachedWeatherProvider:
    return CachedWeatherProvider(OpenMeteoProvider(mock_http.client(), sleep=sleep))


async def test_repeat_geocode_is_served_from_cache(
    mock_http: MockHTTP, no_sleep: RecordingSleep, clock: time_machine.Traveller
) -> None:
    route = mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_warszawa.json"))
    weather = cached(mock_http, no_sleep)

    first = await weather.search_locations("Warszawa")
    clock.shift(timedelta(days=6))
    second = await weather.search_locations("  warszawa ")

    assert second == first
    assert len(route.calls) == 1


async def test_geocode_is_refetched_after_its_ttl(
    mock_http: MockHTTP, no_sleep: RecordingSleep, clock: time_machine.Traveller
) -> None:
    route = mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_warszawa.json"))
    weather = cached(mock_http, no_sleep)

    await weather.search_locations("Warszawa")
    clock.shift(timedelta(days=7, seconds=1))
    await weather.search_locations("Warszawa")

    assert len(route.calls) == 2


async def test_different_places_never_share_an_entry(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    # Guards against a key that normalizes too much, e.g. by stripping diacritics.
    route = mock_http.get(GEOCODING_URL, json_reply(200, "open_meteo/geocode_empty.json"))
    weather = cached(mock_http, no_sleep)

    for name in ["Warsaw", "Wrocław", "Wroclaw", "Łódź", "Lodz"]:
        await weather.search_locations(name)

    assert [call.url.params["name"] for call in route.calls] == ["Warsaw", "Wrocław", "Wroclaw", "Łódź", "Lodz"]


def test_geocode_key_keeps_diacritics_and_country() -> None:
    assert geocode_key("Łódź", None, 10, "pl") != geocode_key("Lodz", None, 10, "pl")
    assert geocode_key("Paris", "FR", 10, "en") != geocode_key("Paris", "US", 10, "en")
    assert geocode_key("New  York", "us", 10, "en") == geocode_key("new york", "US", 10, "en")


async def test_forecast_is_cached_for_its_ttl(
    mock_http: MockHTTP, no_sleep: RecordingSleep, clock: time_machine.Traveller
) -> None:
    route = mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))
    weather = cached(mock_http, no_sleep)

    await weather.get_forecast(*WARSAW, NOV_1, NOV_3)
    clock.shift(timedelta(minutes=29))
    await weather.get_forecast(*WARSAW, NOV_1, NOV_3)
    clock.shift(timedelta(minutes=2))
    await weather.get_forecast(*WARSAW, NOV_1, NOV_3)

    assert len(route.calls) == 2


@pytest.mark.parametrize(
    "failure",
    [
        json_reply(429, "open_meteo/error_rate_limited.json"),
        json_reply(503, body={"error": True, "reason": "Service unavailable"}),
    ],
    ids=["rate-limited", "server-error"],
)
async def test_failure_serves_the_stale_copy_marked_stale(
    mock_http: MockHTTP, no_sleep: RecordingSleep, clock: time_machine.Traveller, failure: httpx2.Response
) -> None:
    mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"), failure)
    weather = cached(mock_http, no_sleep)

    fresh = await weather.get_forecast(*WARSAW, NOV_1, NOV_3)
    clock.shift(timedelta(minutes=45))
    stale = await weather.get_forecast(*WARSAW, NOV_1, NOV_3)

    assert stale.stale is True
    assert stale.fetched_at == fresh.fetched_at == NOW
    assert stale.days == fresh.days


async def test_too_old_copy_is_not_served(
    mock_http: MockHTTP, no_sleep: RecordingSleep, clock: time_machine.Traveller
) -> None:
    mock_http.get(
        FORECAST_URL,
        json_reply(200, "open_meteo/forecast_warsaw.json"),
        json_reply(429, "open_meteo/error_rate_limited.json"),
    )
    weather = cached(mock_http, no_sleep)

    await weather.get_forecast(*WARSAW, NOV_1, NOV_3)
    clock.shift(timedelta(minutes=30) + timedelta(hours=6, seconds=1))

    with pytest.raises(RateLimitedError):
        await weather.get_forecast(*WARSAW, NOV_1, NOV_3)


async def test_rate_limit_without_any_cached_copy_raises(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    mock_http.get(GEOCODING_URL, json_reply(429, "open_meteo/error_rate_limited.json"))

    with pytest.raises(RateLimitedError):
        await cached(mock_http, no_sleep).search_locations("Warszawa")


async def test_invalid_requests_are_not_masked_by_the_cache(
    mock_http: MockHTTP, no_sleep: RecordingSleep, clock: time_machine.Traveller
) -> None:
    mock_http.get(
        FORECAST_URL,
        json_reply(200, "open_meteo/forecast_warsaw.json"),
        json_reply(400, "open_meteo/forecast_error_latitude.json"),
    )
    weather = cached(mock_http, no_sleep)

    await weather.get_forecast(*WARSAW, NOV_1, NOV_3)
    clock.shift(timedelta(hours=1))

    with pytest.raises(InvalidRequestError):
        await weather.get_forecast(*WARSAW, NOV_1, NOV_3)


async def test_geocode_falls_back_to_any_cached_copy(
    mock_http: MockHTTP, no_sleep: RecordingSleep, clock: time_machine.Traveller
) -> None:
    mock_http.get(
        GEOCODING_URL,
        json_reply(200, "open_meteo/geocode_warszawa.json"),
        json_reply(503, body={"error": True, "reason": "Service unavailable"}),
    )
    weather = cached(mock_http, no_sleep)

    first = await weather.search_locations("Warszawa")
    clock.shift(timedelta(days=30))

    assert await weather.search_locations("Warszawa") == first


async def test_upstream_errors_still_raise_when_nothing_is_cached(
    mock_http: MockHTTP, no_sleep: RecordingSleep
) -> None:
    mock_http.get(FORECAST_URL, json_reply(503, body={"error": True, "reason": "Service unavailable"}))

    with pytest.raises(UpstreamUnavailableError):
        await cached(mock_http, no_sleep).get_forecast(*WARSAW, NOV_1, NOV_3)


def test_in_memory_store_evicts_the_least_recently_used_entry() -> None:
    store = InMemoryCacheStore(max_entries=2)
    entry = CacheEntry("{}", NOW)
    store.set("a", entry)
    store.set("b", entry)
    store.get("a")
    store.set("c", entry)

    assert store.get("b") is None
    assert store.get("a") == entry
    assert store.get("c") == entry
