"""Open-Meteo client: geocoding, forecast (today ±) and archive (older dates).

Free tier, no key, non-commercial use only. Data is CC BY 4.0: show "Weather data by Open-Meteo.com"
and, for geocoded places, "Location data based on GeoNames".
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Any, Literal

import httpx2
from pydantic import BaseModel, ValidationError, model_validator

from weather_core.dates import ARCHIVE_EARLIEST, FORECAST_DAYS_AHEAD, FORECAST_DAYS_BACK, utc_now
from weather_core.errors import (
    DateOutOfRangeError,
    InvalidRequestError,
    RateLimitedError,
    UpstreamUnavailableError,
)
from weather_core.models import CurrentConditions, DailyWeather, Forecast, Location, UnitLabels, Units
from weather_core.wmo import describe_weather_code

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

MAX_QUERY_LENGTH = 100
MAX_CANDIDATES = 20
MAX_RANGE_DAYS = 16

_DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
)
# The archive has no precipitation probability.
_ARCHIVE_DAILY_VARIABLES = tuple(v for v in _DAILY_VARIABLES if v != "precipitation_probability_max")
_CURRENT_VARIABLES = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
)
_UNIT_PARAMS = {
    Units.METRIC: {"temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm"},
    Units.IMPERIAL: {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"},
}


class _RawLocation(BaseModel):
    name: str
    latitude: float
    longitude: float
    timezone: str
    country: str | None = None
    country_code: str | None = None
    admin1: str | None = None
    population: int | None = None


class _RawGeocoding(BaseModel):
    # Open-Meteo omits `results` entirely when nothing matches.
    results: list[_RawLocation] = []


class _RawDaily(BaseModel):
    time: list[date]
    weather_code: list[int | None]
    temperature_2m_max: list[float | None]
    temperature_2m_min: list[float | None]
    precipitation_sum: list[float | None]
    precipitation_probability_max: list[int | None] | None = None
    wind_speed_10m_max: list[float | None]

    @model_validator(mode="after")
    def _same_length(self) -> "_RawDaily":
        columns: list[Sequence[object]] = [
            self.weather_code,
            self.temperature_2m_max,
            self.temperature_2m_min,
            self.precipitation_sum,
            self.wind_speed_10m_max,
        ]
        if self.precipitation_probability_max is not None:
            columns.append(self.precipitation_probability_max)
        if any(len(column) != len(self.time) for column in columns):
            raise ValueError("daily columns have different lengths")
        return self


class _RawDailyUnits(BaseModel):
    temperature_2m_max: str
    precipitation_sum: str
    wind_speed_10m_max: str


class _RawCurrent(BaseModel):
    time: datetime
    temperature_2m: float | None = None
    apparent_temperature: float | None = None
    relative_humidity_2m: int | None = None
    precipitation: float | None = None
    weather_code: int | None = None
    wind_speed_10m: float | None = None


class _RawForecast(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    daily_units: _RawDailyUnits
    daily: _RawDaily
    current: _RawCurrent | None = None


class OpenMeteoProvider:
    """Implements `WeatherProvider`. Retries only timeouts, connection errors and 5xx responses."""

    def __init__(
        self,
        client: httpx2.AsyncClient,
        *,
        clock: Callable[[], datetime] = utc_now,
        timeout_seconds: float = 5.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._clock = clock
        self._timeout = httpx2.Timeout(timeout_seconds)
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep

    async def search_locations(
        self,
        query: str,
        *,
        country_code: str | None = None,
        count: int = 10,
        language: str = "en",
    ) -> list[Location]:
        query = query.strip()
        if not query:
            raise InvalidRequestError("The place name is empty.")
        if len(query) > MAX_QUERY_LENGTH:
            raise InvalidRequestError(f"The place name is longer than {MAX_QUERY_LENGTH} characters.")
        if not 1 <= count <= MAX_CANDIDATES:
            raise InvalidRequestError(f"count must be between 1 and {MAX_CANDIDATES}.")

        params: dict[str, str | int] = {"name": query, "count": count, "language": language, "format": "json"}
        if country_code:
            params["countryCode"] = country_code.upper()
        payload = await self._get_json(GEOCODING_URL, params)
        raw = self._parse(_RawGeocoding, payload)
        return [
            Location(
                name=item.name,
                latitude=item.latitude,
                longitude=item.longitude,
                timezone=item.timezone,
                country=item.country,
                country_code=item.country_code,
                region=item.admin1,
                population=item.population,
            )
            for item in raw.results
        ]

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        units: Units = Units.METRIC,
    ) -> Forecast:
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise InvalidRequestError("Latitude must be between -90 and 90 and longitude between -180 and 180.")
        if start_date > end_date:
            raise InvalidRequestError("start_date is after end_date.")
        if (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
            raise InvalidRequestError(f"Ask for at most {MAX_RANGE_DAYS} days at a time.")

        source = self._choose_source(start_date, end_date)
        variables = _DAILY_VARIABLES if source == "forecast" else _ARCHIVE_DAILY_VARIABLES
        params: dict[str, str | float] = {
            # Four decimals (~11 m) is more precision than the weather grid has.
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "daily": ",".join(variables),
            "timezone": "auto",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            **_UNIT_PARAMS[units],
        }
        if source == "forecast" and self._includes_today(start_date, end_date):
            params["current"] = ",".join(_CURRENT_VARIABLES)

        url = FORECAST_URL if source == "forecast" else ARCHIVE_URL
        payload = await self._get_json(url, params)
        raw = self._parse(_RawForecast, payload)
        return self._to_forecast(raw, source)

    def _choose_source(self, start_date: date, end_date: date) -> Literal["forecast", "archive"]:
        # Local "today" can be a day either side of UTC today, so allow one day of slack and let the
        # API reject the true edge cases.
        utc_today = self._clock().date()
        last_forecast_day = utc_today + timedelta(days=FORECAST_DAYS_AHEAD + 1)
        first_forecast_day = utc_today - timedelta(days=FORECAST_DAYS_BACK)

        if end_date > last_forecast_day:
            raise DateOutOfRangeError(
                f"Forecasts reach {FORECAST_DAYS_AHEAD + 1} days ahead, until about {last_forecast_day.isoformat()}."
            )
        if start_date < ARCHIVE_EARLIEST:
            raise DateOutOfRangeError(f"Historical data starts on {ARCHIVE_EARLIEST.isoformat()}.")
        if start_date >= first_forecast_day:
            return "forecast"
        if end_date < first_forecast_day:
            return "archive"
        raise InvalidRequestError(
            f"The range crosses {first_forecast_day.isoformat()}, where forecast data ends and the archive "
            "begins. Ask for the dates before and after it separately."
        )

    def _includes_today(self, start_date: date, end_date: date) -> bool:
        utc_today = self._clock().date()
        return start_date <= utc_today + timedelta(days=1) and end_date >= utc_today - timedelta(days=1)

    def _to_forecast(self, raw: _RawForecast, source: Literal["forecast", "archive"]) -> Forecast:
        daily = raw.daily
        probabilities = daily.precipitation_probability_max or [None] * len(daily.time)
        days = [
            DailyWeather(
                date=day,
                weather_code=daily.weather_code[i],
                weather=describe_weather_code(daily.weather_code[i]),
                temperature_max=daily.temperature_2m_max[i],
                temperature_min=daily.temperature_2m_min[i],
                precipitation_sum=daily.precipitation_sum[i],
                precipitation_probability_max=probabilities[i],
                wind_speed_max=daily.wind_speed_10m_max[i],
            )
            for i, day in enumerate(daily.time)
        ]
        current = None
        if raw.current is not None:
            current = CurrentConditions(
                time=raw.current.time,
                temperature=raw.current.temperature_2m,
                apparent_temperature=raw.current.apparent_temperature,
                relative_humidity=raw.current.relative_humidity_2m,
                precipitation=raw.current.precipitation,
                weather_code=raw.current.weather_code,
                weather=describe_weather_code(raw.current.weather_code),
                wind_speed=raw.current.wind_speed_10m,
            )
        return Forecast(
            latitude=raw.latitude,
            longitude=raw.longitude,
            timezone=raw.timezone,
            units=UnitLabels(
                temperature=raw.daily_units.temperature_2m_max,
                precipitation=raw.daily_units.precipitation_sum,
                wind_speed=raw.daily_units.wind_speed_10m_max,
            ),
            current=current,
            days=days,
            source=source,
            fetched_at=self._clock(),
        )

    async def _get_json(self, url: str, params: dict[str, Any]) -> object:
        attempt = 0
        while True:
            try:
                response = await self._client.get(url, params=params, timeout=self._timeout)
            except (httpx2.TimeoutException, httpx2.TransportError) as exc:
                failure = f"Open-Meteo did not respond ({type(exc).__name__})."
            else:
                if response.status_code < 500:
                    return self._read_body(response)
                failure = f"Open-Meteo returned HTTP {response.status_code}."

            if attempt >= self._max_retries:
                raise UpstreamUnavailableError(f"{failure} Weather data is unavailable right now.")
            await self._sleep(self._backoff_seconds * 2**attempt)
            attempt += 1

    @staticmethod
    def _read_body(response: httpx2.Response) -> object:
        try:
            body: object = response.json()
        except ValueError:
            body = None
        reason = body.get("reason") if isinstance(body, dict) else None

        if response.status_code == 429:
            raise RateLimitedError("Open-Meteo's rate limit was reached. Fresh weather data is unavailable for now.")
        if response.status_code == 400:
            message = reason if isinstance(reason, str) else "Open-Meteo rejected the request."
            if "out of allowed range" in message:
                raise DateOutOfRangeError(message)
            raise InvalidRequestError(message)
        if response.status_code != 200 or body is None:
            raise UpstreamUnavailableError(f"Open-Meteo returned an unexpected HTTP {response.status_code} response.")
        return body

    @staticmethod
    def _parse[M: BaseModel](model: type[M], payload: object) -> M:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise UpstreamUnavailableError("Open-Meteo returned data in an unexpected format.") from exc
