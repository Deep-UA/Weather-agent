"""Checks against the real Open-Meteo API. Run by hand with `uv run pytest -m live`.

Excluded from the default run and from PR CI (they need the network and the API's goodwill). They
catch what fixtures can't: a changed response shape, a changed error message, or drifting data.
"""

from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta

import httpx2
import pytest

from weather_core.dates import local_today, utc_now
from weather_core.errors import DateOutOfRangeError
from weather_core.models import Forecast, Units
from weather_core.open_meteo import OpenMeteoProvider
from weather_core.tools import geo_search_location

pytestmark = [pytest.mark.live, pytest.mark.anyio]

WARSAW = (52.2298, 21.0118)


@pytest.fixture
async def client() -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient() as client:
        yield client


def assert_plausible(forecast: Forecast, *, fahrenheit: bool = False) -> None:
    low, high = (-76, 140) if fahrenheit else (-60, 60)
    for day in forecast.days:
        assert day.temperature_min is not None, day
        assert day.temperature_max is not None, day
        assert low <= day.temperature_min <= day.temperature_max <= high, day
        assert day.precipitation_sum is None or day.precipitation_sum >= 0, day
        assert day.wind_speed_max is None or day.wind_speed_max >= 0, day
        if day.precipitation_probability_max is not None:
            assert 0 <= day.precipitation_probability_max <= 100, day
        assert day.weather is not None, day
        assert not day.weather.startswith("Unknown"), day


@pytest.mark.parametrize(
    ("query", "language", "country_code", "ambiguous"),
    [
        ("Warszawa", "pl", "PL", False),
        ("Lodz", "pl", "PL", False),  # diacritics are optional
        ("Київ", "uk", "UA", False),  # Cyrillic input
        ("Paris", "en", "FR", False),
        ("Springfield", "en", "US", True),
    ],
)
async def test_geocoding(
    client: httpx2.AsyncClient, query: str, language: str, country_code: str, ambiguous: bool
) -> None:
    search = await geo_search_location(OpenMeteoProvider(client), query, language=language)

    assert search.best_match is not None
    assert search.best_match.country_code == country_code
    assert search.ambiguous is ambiguous


async def test_unknown_place_has_no_match(client: httpx2.AsyncClient) -> None:
    search = await geo_search_location(OpenMeteoProvider(client), "Xyzzyqqplorf")

    assert search.best_match is None


async def test_forecast_for_the_next_three_days(client: httpx2.AsyncClient) -> None:
    today = local_today(utc_now(), "Europe/Warsaw")

    forecast = await OpenMeteoProvider(client).get_forecast(*WARSAW, today, today + timedelta(days=2))

    assert [day.date for day in forecast.days] == [today + timedelta(days=n) for n in range(3)]
    assert (forecast.units.temperature, forecast.units.wind_speed, forecast.units.precipitation) == ("°C", "km/h", "mm")
    assert forecast.timezone == "Europe/Warsaw"
    assert forecast.current is not None
    assert_plausible(forecast)


@pytest.mark.parametrize(
    ("latitude", "longitude", "timezone"),
    [(-36.8485, 174.7633, "Pacific/Auckland"), (69.6496, 18.9560, "Europe/Oslo")],
    ids=["southern-hemisphere", "high-latitude"],
)
async def test_forecast_far_from_home(
    client: httpx2.AsyncClient, latitude: float, longitude: float, timezone: str
) -> None:
    today = local_today(utc_now(), timezone)

    forecast = await OpenMeteoProvider(client).get_forecast(latitude, longitude, today, today + timedelta(days=1))

    assert forecast.timezone == timezone
    assert_plausible(forecast)


async def test_imperial_matches_metric(client: httpx2.AsyncClient) -> None:
    # Metamorphic check: F = C x 9/5 + 32, within the API's 0.1-degree rounding.
    provider = OpenMeteoProvider(client)
    today = local_today(utc_now(), "Europe/Warsaw")

    metric = await provider.get_forecast(*WARSAW, today, today + timedelta(days=1))
    imperial = await provider.get_forecast(*WARSAW, today, today + timedelta(days=1), Units.IMPERIAL)

    # Open-Meteo's own label for miles per hour is "mp/h".
    assert (imperial.units.temperature, imperial.units.wind_speed, imperial.units.precipitation) == (
        "°F",
        "mp/h",
        "inch",
    )
    assert_plausible(imperial, fahrenheit=True)
    for c_day, f_day in zip(metric.days, imperial.days, strict=True):
        assert c_day.temperature_max is not None
        assert f_day.temperature_max is not None
        assert f_day.temperature_max == pytest.approx(c_day.temperature_max * 9 / 5 + 32, abs=0.3)


async def test_archive_matches_the_captured_fixture(client: httpx2.AsyncClient) -> None:
    # Historical values can be revised slightly when reanalysis data is finalized.
    forecast = await OpenMeteoProvider(client).get_forecast(*WARSAW, date(2026, 5, 1), date(2026, 5, 2))

    assert forecast.source == "archive"
    assert [day.temperature_max for day in forecast.days] == [
        pytest.approx(20.7, abs=1.0),
        pytest.approx(24.8, abs=1.0),
    ]


async def test_real_out_of_range_error_is_still_recognized(client: httpx2.AsyncClient) -> None:
    # Pretend it's a month from now so the client-side check lets the request through, and the real
    # API's 400 message has to be recognized as a date-range error.
    def future() -> datetime:
        return utc_now() + timedelta(days=30)

    target = utc_now().date() + timedelta(days=25)
    with pytest.raises(DateOutOfRangeError, match="out of allowed range"):
        await OpenMeteoProvider(client, clock=future).get_forecast(*WARSAW, target, target)
