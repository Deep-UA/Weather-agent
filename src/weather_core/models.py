"""Compact, typed weather data: what providers return and what the agent's tools hand to the model."""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Units(StrEnum):
    METRIC = "metric"
    IMPERIAL = "imperial"


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    population: int | None = None


class UnitLabels(BaseModel):
    model_config = ConfigDict(frozen=True)

    temperature: str
    precipitation: str
    wind_speed: str


class CurrentConditions(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: datetime = Field(description="Local time at the location")
    temperature: float | None
    apparent_temperature: float | None
    relative_humidity: int | None
    precipitation: float | None
    weather_code: int | None
    weather: str | None
    wind_speed: float | None


class DailyWeather(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    weather_code: int | None
    weather: str | None
    temperature_max: float | None
    temperature_min: float | None
    precipitation_sum: float | None
    precipitation_probability_max: int | None = Field(description="Not available for archive data")
    wind_speed_max: float | None


class Forecast(BaseModel):
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(description="Grid point the data is for; may differ slightly from the request")
    longitude: float
    timezone: str
    units: UnitLabels
    current: CurrentConditions | None
    days: list[DailyWeather]
    source: Literal["forecast", "archive"]
    fetched_at: datetime
    stale: bool = Field(default=False, description="True when served from cache because the provider failed")
