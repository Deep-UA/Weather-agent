from datetime import date

import httpx2
import pytest

from tests.support.fakes import FIXTURE_DAY, RecordingSleep
from tests.support.mock_http import MockHTTP, json_reply
from weather_core.errors import (
    DateOutOfRangeError,
    InvalidRequestError,
    RateLimitedError,
    UpstreamUnavailableError,
    WeatherError,
)
from weather_core.models import Units
from weather_core.open_meteo import ARCHIVE_URL, FORECAST_URL, OpenMeteoProvider

pytestmark = [pytest.mark.unit, pytest.mark.anyio]

NOW = FIXTURE_DAY
WARSAW = (52.2298, 21.0118)


def provider(mock_http: MockHTTP, sleep: RecordingSleep) -> OpenMeteoProvider:
    return OpenMeteoProvider(mock_http.client(), sleep=sleep)


async def test_forecast_is_parsed_with_units_and_descriptions(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    forecast = await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 11, 1), date(2026, 11, 3))

    assert forecast.source == "forecast"
    assert forecast.timezone == "Europe/Warsaw"
    assert (forecast.units.temperature, forecast.units.wind_speed) == ("°C", "km/h")
    assert [day.date for day in forecast.days] == [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)]
    tuesday = forecast.days[2]
    assert (tuesday.temperature_max, tuesday.temperature_min, tuesday.wind_speed_max) == (9.9, 4.1, 14.8)
    assert forecast.days[1].weather == "Light drizzle"
    assert forecast.current is not None
    assert (forecast.current.temperature, forecast.current.weather) == (8.8, "Overcast")
    assert forecast.fetched_at == NOW
    assert route.last_params["timezone"] == "auto"
    assert "current" in route.last_params


async def test_imperial_units_are_requested(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 11, 1), date(2026, 11, 3), Units.IMPERIAL)

    params = route.last_params
    assert (params["temperature_unit"], params["wind_speed_unit"], params["precipitation_unit"]) == (
        "fahrenheit",
        "mph",
        "inch",
    )


async def test_coordinates_are_rounded_to_four_decimals(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    await provider(mock_http, no_sleep).get_forecast(52.229812345, 21.011812345, date(2026, 11, 1), date(2026, 11, 3))

    assert (route.last_params["latitude"], route.last_params["longitude"]) == ("52.2298", "21.0118")


async def test_recent_past_uses_the_forecast_endpoint(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(FORECAST_URL, json_reply(200, "open_meteo/forecast_warsaw.json"))

    forecast = await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 10, 27), date(2026, 10, 27))

    assert forecast.source == "forecast"
    # "Last Tuesday" doesn't need current conditions.
    assert "current" not in route.last_params


async def test_old_dates_use_the_archive(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(ARCHIVE_URL, json_reply(200, "open_meteo/archive_warsaw.json"))

    forecast = await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 5, 1), date(2026, 5, 2))

    assert forecast.source == "archive"
    assert forecast.current is None
    assert [day.temperature_max for day in forecast.days] == [20.7, 24.8]
    assert all(day.precipitation_probability_max is None for day in forecast.days)
    assert "precipitation_probability_max" not in route.last_params["daily"]


@pytest.mark.parametrize(
    ("start", "end", "error", "message"),
    [
        (date(2026, 12, 30), date(2026, 12, 31), DateOutOfRangeError, "until about 2026-11-17"),
        (date(1939, 12, 31), date(1940, 1, 2), DateOutOfRangeError, "starts on 1940-01-01"),
        (date(2026, 7, 30), date(2026, 8, 5), InvalidRequestError, "crosses 2026-08-01"),
        (date(2026, 11, 3), date(2026, 11, 1), InvalidRequestError, "after end_date"),
        (date(2026, 11, 1), date(2026, 11, 17), InvalidRequestError, "at most 16 days"),
    ],
)
async def test_impossible_ranges_fail_before_any_call(
    mock_http: MockHTTP,
    no_sleep: RecordingSleep,
    start: date,
    end: date,
    error: type[WeatherError],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        await provider(mock_http, no_sleep).get_forecast(*WARSAW, start, end)


async def test_out_of_range_coordinates_fail_before_any_call(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    with pytest.raises(InvalidRequestError, match="Latitude must be between"):
        await provider(mock_http, no_sleep).get_forecast(91, 21, date(2026, 11, 1), date(2026, 11, 1))


@pytest.mark.parametrize(
    ("fixture", "error", "message"),
    [
        ("open_meteo/forecast_error_date_out_of_range.json", DateOutOfRangeError, "out of allowed range"),
        ("open_meteo/forecast_error_latitude.json", InvalidRequestError, "Latitude must be in range"),
    ],
)
async def test_api_400_reason_becomes_the_error_message(
    mock_http: MockHTTP, no_sleep: RecordingSleep, fixture: str, error: type[WeatherError], message: str
) -> None:
    route = mock_http.get(FORECAST_URL, json_reply(400, fixture))

    with pytest.raises(error, match=message):
        await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 11, 15), date(2026, 11, 16))
    assert len(route.calls) == 1


async def test_rate_limit_is_not_retried(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(FORECAST_URL, json_reply(429, "open_meteo/error_rate_limited.json"))

    with pytest.raises(RateLimitedError, match="rate limit"):
        await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 11, 1), date(2026, 11, 3))
    assert len(route.calls) == 1
    assert no_sleep.delays == []


async def test_server_error_is_retried_then_succeeds(mock_http: MockHTTP, no_sleep: RecordingSleep) -> None:
    route = mock_http.get(
        FORECAST_URL,
        json_reply(503, body={"error": True, "reason": "Service unavailable"}),
        json_reply(200, "open_meteo/forecast_warsaw.json"),
    )

    forecast = await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 11, 1), date(2026, 11, 3))

    assert len(forecast.days) == 3
    assert len(route.calls) == 2
    assert no_sleep.delays == [0.5]


@pytest.mark.parametrize("transport_error", [httpx2.ConnectTimeout, httpx2.ReadTimeout, httpx2.ConnectError])
async def test_retries_are_bounded(
    mock_http: MockHTTP, no_sleep: RecordingSleep, transport_error: type[httpx2.TransportError]
) -> None:
    route = mock_http.get(FORECAST_URL, transport_error)

    with pytest.raises(UpstreamUnavailableError, match="did not respond"):
        await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 11, 1), date(2026, 11, 3))
    assert len(route.calls) == 3
    assert no_sleep.delays == [0.5, 1.0]


@pytest.mark.parametrize(
    "reply",
    [
        httpx2.Response(200, text="<html>Bad gateway</html>"),
        httpx2.Response(200, json={"latitude": 52.2, "longitude": 21.0}),
        httpx2.Response(
            200,
            json={
                "latitude": 52.2,
                "longitude": 21.0,
                "timezone": "Europe/Warsaw",
                "daily_units": {"temperature_2m_max": "°C", "precipitation_sum": "mm", "wind_speed_10m_max": "km/h"},
                "daily": {
                    "time": ["2026-11-01", "2026-11-02"],
                    "weather_code": [3],
                    "temperature_2m_max": [9.1, 7.7],
                    "temperature_2m_min": [5.8, 6.1],
                    "precipitation_sum": [0.0, 0.6],
                    "wind_speed_10m_max": [11.9, 9.0],
                },
            },
        ),
        httpx2.Response(404, text="Not found"),
    ],
    ids=["not-json", "missing-daily", "ragged-columns", "http-404"],
)
async def test_unusable_responses_become_upstream_errors(
    mock_http: MockHTTP, no_sleep: RecordingSleep, reply: httpx2.Response
) -> None:
    mock_http.get(FORECAST_URL, reply)

    with pytest.raises(UpstreamUnavailableError):
        await provider(mock_http, no_sleep).get_forecast(*WARSAW, date(2026, 11, 1), date(2026, 11, 2))
