"""The interface every weather data source implements, so a fallback provider can be added later."""

from datetime import date
from typing import Protocol

from weather_core.models import Forecast, Location, Units


class WeatherProvider(Protocol):
    async def search_locations(
        self,
        query: str,
        *,
        country_code: str | None = None,
        count: int = 10,
        language: str = "en",
    ) -> list[Location]:
        """Candidate places for `query`, most relevant first. An empty list means no match."""
        ...

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        units: Units = Units.METRIC,
    ) -> Forecast:
        """Daily weather for each date in the range, local to the location, plus current conditions
        when the range includes today. Raises a `WeatherError` subclass on failure."""
        ...
