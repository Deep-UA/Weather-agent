from datetime import UTC, datetime

# Midday UTC on the day the Open-Meteo fixtures were captured.
FIXTURE_DAY = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class RecordingSleep:
    """A drop-in for `asyncio.sleep` that returns at once and records each delay."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
