"""Guards on the request body the agent actually sends to the Claude API.

Claude Haiku 5.5 returns HTTP 400 for `temperature`, `top_p` or `top_k`, so a request carrying one
would fail every user turn. These tests capture the real wire body through a mock transport.
"""

import json
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest
from pydantic_ai import Agent, models
from pydantic_ai.models.anthropic import AnthropicModelSettings

from weather_agent.model import MODEL_NAME, MODEL_SETTINGS, build_model

pytestmark = pytest.mark.security

SAMPLING_PARAMS = frozenset({"temperature", "top_p", "top_k"})
EFFORT_ALLOWED_WITH_THINKING_DISABLED = frozenset({"low", "medium", "high"})

MINIMAL_MESSAGE = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": MODEL_NAME,
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 2},
}


def find_sampling_params(node: object, path: str = "$") -> list[str]:
    """Return the JSON path of every sampling-parameter key anywhere in `node`."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in SAMPLING_PARAMS:
                found.append(f"{path}.{key}")
            found.extend(find_sampling_params(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(find_sampling_params(item, f"{path}[{index}]"))
    return found


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"model": MODEL_NAME, "max_tokens": 10}, []),
        ({"temperature": 0}, ["$.temperature"]),
        ({"output_config": {"top_p": 0.9}}, ["$.output_config.top_p"]),
        ({"messages": [{"content": [{"top_k": 5}]}]}, ["$.messages[0].content[0].top_k"]),
        # A field that merely mentions the word is not a sampling parameter.
        ({"system": [{"text": "Set temperature in °C"}]}, []),
    ],
)
def test_find_sampling_params(body: dict[str, Any], expected: list[str]) -> None:
    # The guard below can only fail if this detector can; prove it on known bodies first.
    assert find_sampling_params(body) == expected


@pytest.fixture
def captured_requests() -> Iterator[list[httpx2.Request]]:
    with models.override_allow_model_requests(True):
        yield []


async def run_once(captured: list[httpx2.Request], settings: AnthropicModelSettings) -> dict[str, Any]:
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, json=MINIMAL_MESSAGE)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    agent = Agent(build_model(api_key="test", http_client=client), model_settings=settings, instructions="Be brief.")
    await agent.run("What's the weather in Warsaw?")
    assert len(captured) == 1
    body: dict[str, Any] = json.loads(captured[0].content)
    return body


@pytest.mark.anyio
async def test_request_matches_the_locked_model_config(captured_requests: list[httpx2.Request]) -> None:
    body = await run_once(captured_requests, MODEL_SETTINGS)

    assert find_sampling_params(body) == []
    assert body["model"] == MODEL_NAME
    assert body["thinking"] == {"type": "disabled"}
    if "output_config" in body and "effort" in body["output_config"]:
        assert body["output_config"]["effort"] in EFFORT_ALLOWED_WITH_THINKING_DISABLED
    assert body["system"][-1]["cache_control"]["type"] == "ephemeral"


@pytest.mark.anyio
async def test_sampling_settings_never_reach_the_wire(captured_requests: list[httpx2.Request]) -> None:
    # A future edit that adds sampling settings, directly or through `extra_body`, must not turn into
    # a 400 for every user.
    leaky = AnthropicModelSettings(**MODEL_SETTINGS, temperature=0.0, top_p=0.9, extra_body={"top_k": 5})

    with pytest.warns(UserWarning, match="Sampling parameters"):
        body = await run_once(captured_requests, leaky)

    assert find_sampling_params(body) == []
