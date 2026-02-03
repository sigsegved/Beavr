"""LLM client abstraction for AI Investor.

Uses GitHub Copilot SDK for LLM inference. This provides access to
GPT-5, Claude Sonnet, and other models via your existing GitHub Copilot subscription.
No separate API key needed - uses your existing Copilot CLI authentication!
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMConfig(BaseModel):
    """Configuration for LLM client."""

    model: str = Field(default="gpt-4.1", description="Model to use (gpt-5, gpt-4.1, claude-sonnet-4.5)")
    temperature: float = Field(default=0.3, description="Sampling temperature")
    max_tokens: int = Field(default=2000, description="Max tokens in response")
    timeout: float = Field(default=60.0, description="Request timeout")


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
        except ImportError:
            raise ImportError(
                "github-copilot-sdk package required for AI Investor. "
                "Install with: pip install github-copilot-sdk"
            )

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
        import concurrent.futures
        
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

        # Use send_and_wait for simplicity
        response = await self._session.send_and_wait(
            {"prompt": full_prompt},
            timeout=self.config.timeout
        )

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

        response = await self._session.send_and_wait(
            {"prompt": full_prompt},
            timeout=self.config.timeout
        )
        
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
