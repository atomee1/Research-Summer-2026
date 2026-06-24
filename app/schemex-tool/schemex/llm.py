"""Thin wrapper around the Anthropic API.

Only one assumption is baked in: every call to the model in this tool
wants either free-text back, or a single JSON object/array back. We ask
for JSON explicitly in the prompt and then parse defensively, since
models occasionally wrap JSON in prose or code fences despite being
asked not to.

Set ANTHROPIC_API_KEY in your environment before running. The default
model can be overridden with --model on the CLI or the SCHEMEX_MODEL
env var. Check https://docs.claude.com for the current list of model
names -- the default below may not be the latest model by the time you
read this.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

try:
    import anthropic
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The 'anthropic' package is required. Install with:\n"
        "    pip install anthropic"
    ) from exc

DEFAULT_MODEL = os.environ.get("SCHEMEX_MODEL", "claude-sonnet-4-6")
DEFAULT_MAX_TOKENS = 4096


class LLMError(RuntimeError):
    pass


class ClaudeClient:
    """Wraps anthropic.Anthropic with a couple of convenience methods."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        api_key: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.verbose = verbose
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "No API key found. Set the ANTHROPIC_API_KEY environment "
                "variable, or pass --api-key on the command line."
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, user: str) -> str:
        """Single-turn completion. Returns the concatenated text blocks."""
        if self.verbose:
            print(f"\n--- LLM call (model={self.model}) ---")
            print("SYSTEM:", system[:300], "..." if len(system) > 300 else "")
            print("USER:", user[:500], "..." if len(user) > 500 else "")

        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        if self.verbose:
            print("RESPONSE:", text[:800], "..." if len(text) > 800 else "")
        return text

    def complete_json(self, system: str, user: str) -> Any:
        """Completion where the model is instructed to return pure JSON.

        Strips markdown code fences and any leading/trailing prose the
        model adds despite instructions, then parses. Raises LLMError
        with the raw text attached if parsing still fails, so callers
        can decide whether to retry or surface it to the user.
        """
        json_instruction = (
            "\n\nRespond with ONLY a single valid JSON value (object or "
            "array). Do not include any prose, explanation, or markdown "
            "code fences before or after the JSON."
        )
        raw = self.complete(system, user + json_instruction)
        parsed = _extract_json(raw)
        if parsed is None:
            raise LLMError(f"Could not parse JSON from model response:\n{raw}")
        return parsed


def _extract_json(raw: str) -> Optional[Any]:
    """Best-effort extraction of a JSON value from a model response."""
    text = raw.strip()

    # Strip ```json ... ``` or ``` ... ``` fences if present.
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to grabbing the largest {...} or [...] span in the text.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    return None