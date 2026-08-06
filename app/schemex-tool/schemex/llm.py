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
from typing import Any, Dict, List, Optional

try:
    import anthropic
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The 'anthropic' package is required. Install with:\n"
        "    pip install anthropic"
    ) from exc

DEFAULT_MODEL = os.environ.get("SCHEMEX_MODEL", "claude-sonnet-4-6")
DEFAULT_MAX_TOKENS = 4096

# Anthropic's server-side web search tool -- Claude decides on its own whether
# a given call actually needs to search; declaring the tool just makes the
# capability available. `max_uses` bounds it to a few searches per call so an
# "on" toggle in the UI can't run away with cost/latency. Requires a model
# that supports the dynamic-filtering search tool (Sonnet 4.6+/Opus 4.6+ and
# newer) -- schemex's default model qualifies.
SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}


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
        # Sources from the most recent completion, if use_search=True was
        # passed -- a side-channel rather than a return value so every
        # existing complete()/complete_json() call site keeps working
        # unchanged; callers that care read this right after the call.
        self.last_search_sources: List[Dict[str, str]] = []

    def complete(self, system: str, user: str, use_search: bool = False) -> str:
        """Single-turn completion. Returns the concatenated text blocks."""
        if self.verbose:
            print(f"\n--- LLM call (model={self.model}, search={use_search}) ---")
            print("SYSTEM:", system[:300], "..." if len(system) > 300 else "")
            print("USER:", user[:500], "..." if len(user) > 500 else "")

        kwargs = {"tools": [SEARCH_TOOL]} if use_search else {}
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            **kwargs,
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        self.last_search_sources = _extract_search_sources(response) if use_search else []
        if self.verbose:
            print("RESPONSE:", text[:800], "..." if len(text) > 800 else "")
        return text

    def complete_json(self, system: str, user: str, use_search: bool = False) -> Any:
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
        raw = self.complete(system, user + json_instruction, use_search=use_search)
        parsed = _extract_json(raw)
        if parsed is None:
            raise LLMError(f"Could not parse JSON from model response:\n{raw}")
        return parsed


def _extract_search_sources(response: Any) -> List[Dict[str, str]]:
    """Pull {title, url} out of any web_search_tool_result blocks in a
    response. On a search-tool error (e.g. max_uses_exceeded), `.content`
    is a single error object rather than a list -- skip those rather than
    surfacing the raw error as a fake source."""
    sources: List[Dict[str, str]] = []
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        content = getattr(block, "content", None)
        if not isinstance(content, list):
            continue
        for item in content:
            if getattr(item, "type", None) == "web_search_result":
                sources.append({
                    "title": getattr(item, "title", "") or "",
                    "url": getattr(item, "url", "") or "",
                })
    return sources


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