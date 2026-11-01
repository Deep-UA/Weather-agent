"""Errors raised by weather providers.

`str(error)` is always a short, specific message the agent can act on or pass to the user. Nothing
here carries a stack trace or a raw response body.
"""


class WeatherError(Exception):
    """Base class for every expected weather-data failure."""


class InvalidRequestError(WeatherError):
    """The request can't be served as asked; changing the arguments may fix it."""


class DateOutOfRangeError(InvalidRequestError):
    """The requested dates are outside what the provider covers."""


class RateLimitedError(WeatherError):
    """The provider refused the request because of its rate limit. Retrying soon won't help."""


class UpstreamUnavailableError(WeatherError):
    """The provider timed out, failed, or returned something unusable."""
