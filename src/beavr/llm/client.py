"""LLM client abstraction for AI Investor.

Uses GitHub Copilot SDK for LLM inference. This provides access to
GPT-5, Claude Sonnet, and other models via your existing GitHub Copilot subscription.
No separate API key needed - uses your existing Copilot CLI authentication!

Supports per-agent model configuration for cost/quality optimization.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional, TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMConfig(BaseModel):
    """Configuration for LLM client."""

    model: str = Field(default="gpt-4o", description="Model to use (gpt-4o, gpt-4o-mini, claude-sonnet-4-20250514)")
    temperature: float = Field(default=0.3, description="Sampling temperature")
    max_tokens: int = Field(default=2000, description="Max tokens in response")
    timeout: float = Field(default=60.0, description="Request timeout")
    provider: str = Field(default="copilot", description="LLM provider (copilot, openai, anthropic)")


# Per-agent model defaults (can be overridden via config)
AGENT_MODEL_DEFAULTS: dict[str, str] = {
    "news_monitor": "gpt-4o-mini",
    "thesis_generator": "gpt-4o",
    "due_diligence": "claude-sonnet-4-20250514",  # Best for deep research
    "morning_scanner": "gpt-4o-mini",
    "position_manager": "gpt-4o",
    "trade_executor": "gpt-4o-mini",
    "market_analyst": "gpt-4o",
    "swing_trader": "gpt-4o-mini",
}


def get_agent_config(agent_name: str, config_path: Optional[Path] = None) -> LLMConfig:
    """
    Get LLM configuration for a specific agent.
    
    Args:
        agent_name: Name of the agent (e.g., 'due_diligence', 'news_monitor')
        config_path: Optional path to config file
        
    Returns:
        LLMConfig with agent-specific settings
    """
    # Normalize agent name
    agent_key = agent_name.lower().replace(" ", "_").replace("agent", "").strip("_")

    # Default model for this agent
    default_model = AGENT_MODEL_DEFAULTS.get(agent_key, "gpt-4o")

    # Try to load from config file
    if config_path and config_path.exists():
        try:
            import tomllib
            with open(config_path, "rb") as f:
                config_data = tomllib.load(f)

            llm_config = config_data.get("llm", {})
            models = llm_config.get("models", {})
            model_settings = llm_config.get("model_settings", {})

            # Get agent-specific model
            model = models.get(agent_key, llm_config.get("default_model", default_model))

            # Get model-specific settings
            settings = model_settings.get(model, {})

            return LLMConfig(
                model=model,
                temperature=settings.get("temperature", 0.3),
                max_tokens=settings.get("max_completion_tokens", 2000),
                timeout=llm_config.get("timeout_seconds", 60.0),
                provider=llm_config.get("provider", "copilot"),
            )
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")

    # Return default config for agent
    return LLMConfig(
        model=default_model,
        temperature=0.3 if "mini" in default_model else 0.4,
        max_tokens=4096 if "claude" in default_model else 2000,
    )


class LLMClient:
    """
    LLM client for AI Investor agents using GitHub Copilot SDK.

    Uses your GitHub Copilot subscription - no separate API key needed!
    Authentication is handled by the Copilot CLI.
    """

    _loop: Any = None
    _loop_thread: Any = None

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize LLM client.

        Args:
            config: Optional configuration
        """
        try:
            from copilot import CopilotClient  # type: ignore[import-not-found]
            self._CopilotClient = CopilotClient
        except ImportError as e:
            raise ImportError(
                "github-copilot-sdk package required for AI Investor. "
                "Install with: pip install github-copilot-sdk"
            ) from e

        self.config = config or LLMConfig()
        self._client: Any = None
        self._session: Any = None
        self._initialized = False

        # Create a dedicated event loop for this client
        self._setup_event_loop()

    def _setup_event_loop(self):
        """Set up a dedicated event loop in a background thread."""
        import threading

        if LLMClient._loop is None or LLMClient._loop.is_closed():
            LLMClient._loop = asyncio.new_event_loop()

            def run_loop():
                asyncio.set_event_loop(LLMClient._loop)
                LLMClient._loop.run_forever()

            LLMClient._loop_thread = threading.Thread(target=run_loop, daemon=True)
            LLMClient._loop_thread.start()

    def _run_async(self, coro):
        """Run async code in the dedicated event loop."""

        if LLMClient._loop is None or LLMClient._loop.is_closed():
            self._setup_event_loop()

        future = asyncio.run_coroutine_threadsafe(coro, LLMClient._loop)
        return future.result(timeout=self.config.timeout)

    async def _ensure_session_async(self):
        """Ensure we have an active session (async version)."""
        if self._client is None:
            self._client = self._CopilotClient({"log_level": "error"})
            await self._client.start()

        if self._session is None:
            self._session = await self._client.create_session({"model": self.config.model})

    async def _recreate_session_async(self):
        """Recreate the session if it was lost."""
        try:
            if self._session:
                await self._session.destroy()
        except Exception:
            pass
        self._session = None
        await self._ensure_session_async()

    async def _reason_async(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
    ) -> T:
        """Async implementation of reason()."""
        await self._ensure_session_async()

        # Build JSON schema from Pydantic model
        schema = output_schema.model_json_schema()
        schema_name = output_schema.__name__

        # Build the prompt with JSON schema instructions
        full_prompt = f"""## System Instructions
{system_prompt}

## Task
{user_prompt}

## Response Format
You MUST respond with ONLY valid JSON matching this schema (no markdown, no code blocks, no explanation):

{json.dumps(schema, indent=2)}

Return your analysis as valid JSON now:"""

        # Use send_and_wait for simplicity, with retry on session errors
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                response = await self._session.send_and_wait(
                    {"prompt": full_prompt},
                    timeout=self.config.timeout
                )
                break
            except Exception as e:
                last_error = e
                error_str = str(e)
                # Check for session not found error
                if "Session not found" in error_str or "session" in error_str.lower():
                    logger.debug(f"Session error, recreating session (attempt {attempt + 1})")
                    await self._recreate_session_async()
                else:
                    raise
        else:
            raise RuntimeError(f"Failed after {max_retries} retries: {last_error}")

        if not response or not response.data.content:
            raise RuntimeError("Empty response from LLM")

        response_text = response.data.content

        # Extract JSON from response (handle markdown code blocks)
        json_text = response_text.strip()

        # Remove markdown code blocks if present
        if json_text.startswith("```"):
            lines = json_text.split("\n")
            start_idx = 1
            end_idx = len(lines)
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "```":
                    end_idx = i
                    break
            json_text = "\n".join(lines[start_idx:end_idx]).strip()

        try:
            args = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Raw response: {response_text}")
            raise RuntimeError(f"Invalid JSON from LLM: {e}") from e

        logger.debug(f"LLM response for {schema_name}: {args}")

        # Validate with Pydantic
        return output_schema.model_validate(args)

    def reason(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
    ) -> T:
        """
        Execute LLM reasoning with structured output.

        Sends a prompt to Copilot and parses the JSON response
        into a Pydantic model.

        Args:
            system_prompt: Agent persona/instructions
            user_prompt: Context and question
            output_schema: Pydantic model for response validation

        Returns:
            Validated instance of output_schema

        Raises:
            RuntimeError: If model fails to return valid structured output
        """
        return self._run_async(self._reason_async(system_prompt, user_prompt, output_schema))

    async def _complete_async(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Async implementation of complete()."""
        await self._ensure_session_async()

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                response = await self._session.send_and_wait(
                    {"prompt": full_prompt},
                    timeout=self.config.timeout
                )
                break
            except Exception as e:
                last_error = e
                error_str = str(e)
                if "Session not found" in error_str or "session" in error_str.lower():
                    logger.debug(f"Session error in complete(), recreating (attempt {attempt + 1})")
                    await self._recreate_session_async()
                else:
                    raise
        else:
            raise RuntimeError(f"Failed after {max_retries} retries: {last_error}")

        if not response or not response.data.content:
            return ""

        return response.data.content

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Simple text completion without structured output.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            Text response
        """
        return self._run_async(self._complete_async(prompt, system_prompt))

    async def _close_async(self):
        """Async cleanup."""
        if self._session:
            await self._session.destroy()
            self._session = None
        if self._client:
            await self._client.stop()
            self._client = None
        self._initialized = False

    def close(self):
        """Clean up resources."""
        if self._session or self._client:
            try:
                self._run_async(self._close_async())
            except Exception:
                pass

    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except Exception:
            pass
