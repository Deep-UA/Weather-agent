"""The one place the Claude model and its request settings are defined.

Claude Haiku 5.5 rejects `temperature`, `top_p` and `top_k`, and from API version 2026-10-21 every
model does, so nothing here sets them. Determinism in tests comes from fake models and mocked HTTP,
not from sampling parameters.
"""

import httpx2
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

MODEL_NAME = "claude-haiku-5-5"

MODEL_SETTINGS = AnthropicModelSettings(
    # A two-tool weather lookup doesn't need reasoning; disabling thinking saves latency and output
    # tokens. Haiku 5.5 accepts disabled thinking only at effort `high` or below.
    anthropic_thinking={"type": "disabled"},
    # Haiku 5.5 defaults to `medium`; set it explicitly so a default change can't move it.
    anthropic_effort="medium",
    max_tokens=1024,
    # The system prompt and tool definitions repeat on every request, so cache them.
    anthropic_cache_instructions=True,
    anthropic_cache_tool_definitions=True,
)


def build_model(*, api_key: str | None = None, http_client: httpx2.AsyncClient | None = None) -> AnthropicModel:
    """Build the agent's model. Tests pass an `http_client` with a mock transport."""
    provider = AnthropicProvider(api_key=api_key, http_client=http_client)
    return AnthropicModel(MODEL_NAME, provider=provider)
