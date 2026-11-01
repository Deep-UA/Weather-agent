"""Date arithmetic for forecast windows. Every function takes `now` explicitly so tests can freeze it."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

# Open-Meteo's forecast endpoint serves today plus 15 days ahead and 92 days back; older dates come
# from the archive, which starts in 1940.
FORECAST_DAYS_AHEAD = 15
FORECAST_DAYS_BACK = 92
ARCHIVE_EARLIEST = date(1940, 1, 1)


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_today(now: datetime, timezone: str) -> date:
    """The calendar date at `timezone` when it is `now` (an aware datetime) everywhere."""
    return now.astimezone(ZoneInfo(timezone)).date()


def forecast_window(today: date) -> tuple[date, date]:
    """First and last dates the forecast endpoint serves, relative to `today`."""
    return today - timedelta(days=FORECAST_DAYS_BACK), today + timedelta(days=FORECAST_DAYS_AHEAD)
