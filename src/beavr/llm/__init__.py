"""LLM integration layer for AI Investor."""

from beavr.llm.client import (
    AGENT_MODEL_DEFAULTS,
    LLMClient,
    LLMConfig,
    get_agent_config,
)

__all__ = [
    "AGENT_MODEL_DEFAULTS",
    "LLMClient",
    "LLMConfig",
    "get_agent_config",
]
