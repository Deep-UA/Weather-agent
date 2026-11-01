from datetime import UTC, date, datetime

import pytest
import time_machine

from weather_core.dates import forecast_window, local_today, utc_now
from weather_core.wmo import WMO_CODES, describe_weather_code

pytestmark = pytest.mark.unit

# Already 31 October in Kyiv, still 30 October in New York: the "tomorrow" edge case the agent must get right.
EDGE = datetime(2026, 10, 30, 22, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("timezone", "expected"),
    [
        ("Europe/Kyiv", date(2026, 10, 31)),
        ("Europe/Warsaw", date(2026, 10, 30)),
        ("America/New_York", date(2026, 10, 30)),
        ("Pacific/Auckland", date(2026, 10, 31)),
        ("UTC", date(2026, 10, 30)),
    ],
)
def test_local_today_at_the_utc_midnight_edge(timezone: str, expected: date) -> None:
    with time_machine.travel(EDGE, tick=False):
        assert local_today(utc_now(), timezone) == expected


def test_forecast_window_matches_the_open_meteo_limits() -> None:
    assert forecast_window(date(2026, 11, 1)) == (date(2026, 8, 1), date(2026, 11, 16))


def test_utc_now_is_timezone_aware() -> None:
    assert utc_now().tzinfo is UTC


@pytest.mark.parametrize(
    ("code", "description"),
    [(0, "Clear sky"), (3, "Overcast"), (51, "Light drizzle"), (99, "Thunderstorm with heavy hail")],
)
def test_known_weather_codes(code: int, description: str) -> None:
    assert describe_weather_code(code) == description


def test_unknown_and_missing_weather_codes() -> None:
    assert describe_weather_code(42) == "Unknown weather code 42"
    assert describe_weather_code(None) is None


def test_every_documented_code_is_mapped() -> None:
    documented = {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86}
    assert set(WMO_CODES) == documented | {95, 96, 99}
