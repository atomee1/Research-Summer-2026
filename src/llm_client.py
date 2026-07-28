"""OpenAI-backed helpers for the interactive schema fixer, critique bot,
and advocate/skeptic journalist chat. Reuses the OPENAI_API_KEY / OPENAI_MODEL
env vars already used by src/extract_schema.py.
"""
import json
import os

from openai import OpenAI

from src.schema_models import (
    LIST_FIELDS,
    CritiqueIssue,
    DebateResponse,
    ListFieldFix,
    SchemaCard,
    SchemaCritique,
    TextFieldFix,
)


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY. Add it to your .env file.")
    return OpenAI(api_key=api_key)


def get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def fix_field(
    client: OpenAI,
    model: str,
    field: str,
    current_value,
    article_title: str,
    article_text: str,
    schema: dict,
    instruction: str = "",
):
    """Regenerate a single SchemaCard field, grounded in the source article."""
    is_list = field in LIST_FIELDS
    description = SchemaCard.model_fields[field].description
    instruction_block = f"\nEditor's instruction: {instruction}" if instruction else ""

    system = (
        "You are a meticulous editing assistant helping a journalist fix one field "
        "of a narrative schema extracted from a news article. Improve ONLY the field "
        "requested. Ground every claim in the article text -- do not invent facts "
        "that aren't supported by it."
    )
    user = f"""ARTICLE TITLE: {article_title}

ARTICLE TEXT:
{article_text}

FULL CURRENT SCHEMA (for context):
{json.dumps(schema, indent=2)}

FIELD TO FIX: {field}
FIELD MEANING: {description}
CURRENT VALUE: {current_value!r}
{instruction_block}

Rewrite this field so it is accurate, specific, and well-supported by the article."""

    response_format = ListFieldFix if is_list else TextFieldFix
    completion = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=response_format,
    )
    parsed = completion.choices[0].message.parsed
    return parsed.values if is_list else parsed.value


def critique_schema(
    client: OpenAI,
    model: str,
    article_title: str,
    article_text: str,
    schema: dict,
) -> SchemaCritique:
    """Have the model critique a schema card against its source article."""
    system = (
        "You are a skeptical editor reviewing a narrative schema extracted from a "
        "news article, checking that it is faithful, specific, and free of vague "
        "filler or unsupported claims. Flag fields that are too generic, not "
        "actually supported by the article text, or that skip an important causal "
        "step. Do not flag fields that are already accurate and specific."
    )
    user = f"""ARTICLE TITLE: {article_title}

ARTICLE TEXT:
{article_text}

EXTRACTED SCHEMA:
{json.dumps(schema, indent=2)}

Critique this schema field by field."""
    completion = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=SchemaCritique,
    )
    return completion.choices[0].message.parsed


def debate_reply(
    client: OpenAI,
    model: str,
    article_title: str,
    article_text: str,
    schema: dict,
    history: list[dict],
    question: str,
) -> DebateResponse:
    """Produce two opposing, article-grounded answers to a reporter's question:
    an Advocate who defends the article's framing, and a Skeptic who challenges it.
    """
    system = (
        "You are running a two-sided journalist debate about a news article. "
        "Given a reporter's question, produce TWO opposing answers grounded in the "
        "article: an ADVOCATE who defends and supports the article's framing and "
        "the central actors' actions, and a SKEPTIC who challenges that framing, "
        "raises doubts, and highlights what's missing, one-sided, or self-serving "
        "about it. Both sides must stay grounded in the article's actual facts -- "
        "disagree in interpretation and emphasis, not by inventing new facts."
    )
    history_block = ""
    for turn in history:
        history_block += (
            f"\nREPORTER: {turn['question']}\n"
            f"ADVOCATE: {turn['advocate']}\n"
            f"SKEPTIC: {turn['skeptic']}\n"
        )

    user = f"""ARTICLE TITLE: {article_title}

ARTICLE TEXT:
{article_text}

SCHEMA:
{json.dumps(schema, indent=2)}

PRIOR CONVERSATION:{history_block if history_block else " (none yet)"}

REPORTER'S NEW QUESTION: {question}"""

    completion = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=DebateResponse,
    )
    return completion.choices[0].message.parsed
