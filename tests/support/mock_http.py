"""A route-matching mock for `httpx2` clients.

respx only patches the `httpx` package, and this project's HTTP stack is `httpx2`, so this covers the
two respx checks the tests rely on: every request must match a route, and every route must be called.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

type Reply = httpx2.Response | type[httpx2.TransportError] | Callable[[httpx2.Request], httpx2.Response]


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def json_reply(status_code: int, fixture: str | None = None, *, body: object = None) -> httpx2.Response:
    content = fixture_json(fixture) if fixture is not None else body
    return httpx2.Response(status_code, json=content)


@dataclass
class Route:
    method: str
    url: str
    replies: list[Reply]
    calls: list[httpx2.Request] = field(default_factory=list)

    @property
    def last_params(self) -> dict[str, str]:
        return dict(self.calls[-1].url.params)


class UnmockedRequestError(AssertionError):
    pass


class MockHTTP:
    def __init__(self) -> None:
        self.routes: list[Route] = []

    def get(self, url: str, *replies: Reply) -> Route:
        """Mock GET `url` (query string ignored). Replies are used in order; the last one repeats."""
        route = Route("GET", url, list(replies))
        self.routes.append(route)
        return route

    def client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self._handle))

    def assert_all_called(self) -> None:
        uncalled = [f"{route.method} {route.url}" for route in self.routes if not route.calls]
        assert not uncalled, f"Mocked routes never called: {uncalled}"

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url.copy_with(query=None))
        for route in self.routes:
            if route.method == request.method and route.url == url:
                route.calls.append(request)
                reply = route.replies[min(len(route.calls), len(route.replies)) - 1]
                if isinstance(reply, httpx2.Response):
                    return reply
                if isinstance(reply, type):
                    raise reply("mocked transport error", request=request)
                return reply(request)
        raise UnmockedRequestError(f"Unmocked request: {request.method} {request.url}")
