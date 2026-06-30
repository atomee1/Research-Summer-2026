"""Prompt templates for clustering, abstraction, and refinement.

These mirror the three stages described in the Schemex paper
(arXiv:2502.15105): cluster examples by latent structural similarity,
abstract a Components/Attributes/Relationships schema per cluster, then
refine the schema by generating new examples from it and contrasting
them against real ones.
"""
from __future__ import annotations

from typing import List

from .models import Example, Schema

CLUSTERING_SYSTEM = """You are an expert at schema induction: finding latent \
structural patterns that explain why a set of examples are organized the \
way they are. You are NOT looking for topical similarity (what the examples \
are *about*) -- you are looking for structural similarity (how the examples \
are *built*: what sections/moves they contain, what order those appear in, \
and what kind of evidence or voice each one leans on).

Two examples on the same topic can belong to different clusters if they are \
built differently (e.g. an op-ed and a financial report about the same \
company). Two examples on unrelated topics can belong to the same cluster \
if they are built the same way (e.g. a product launch announcement and an \
M&A rejection both built as Decision -> Actor -> Context -> Quoted \
justification -> Reactions)."""

CLUSTERING_USER_TEMPLATE = """Here are {n} examples, each with an id, title, \
and full text. Group them into clusters based on their LATENT STRUCTURE \
(the recurring shape/moves of the writing), not their topic.

For each cluster, give it a short descriptive name that names the \
structural pattern (not the topic), list the member example ids, and \
explain in 1-3 sentences what structural features the members share and \
what would NOT belong in this cluster.

Examples:
{examples_block}

Return a JSON array of objects, each shaped like:
{{
  "id": "cluster_1",
  "name": "short structural-pattern name",
  "member_ids": ["ex_1", "ex_4", ...],
  "rationale": "why these belong together structurally, and what excludes others"
}}

Every example id must appear in exactly one cluster. Prefer 3-7 clusters \
unless the examples clearly demand more or fewer."""


ABSTRACTION_SYSTEM = """You are an expert at abstracting a reusable schema \
from a set of structurally-similar examples. A schema has three parts:

- Components: the core structural slots that recur across the examples \
  (e.g. "Findings", "Decision", "Quoted justification").
- Attributes: content norms for each component -- what a strong instance \
  of that component actually contains or does, specific enough to be \
  actionable (e.g. "Findings should report at least one number alongside \
  one qualitative observation", not just "describe the results").
- Relationships: the causal or structural link from one component to the \
  next (e.g. "Findings -> Implications: implications must be translated \
  directly from a specific finding, not asserted independently").

The schema should be specific enough that someone could follow it to \
produce a new, convincing example of the same structural pattern -- and \
specific enough that you could point to which examples violate it."""

ABSTRACTION_USER_TEMPLATE = """These examples were clustered together under \
the pattern "{cluster_name}":

{examples_block}

Cluster rationale from the clustering stage: {rationale}

Derive a Components / Attributes / Relationships schema that explains the \
shared structure of these examples. Use 4-7 components.

Return a JSON object shaped like:
{{
  "components": [
    {{
      "name": "Component name",
      "attributes": ["content norm 1", "content norm 2", ...],
      "relationship_to_next": "how this component leads into the next one"
    }},
    ...
  ],
  "notes": "anything notable: outliers in this cluster, ambiguity, etc."
}}"""


GENERATION_SYSTEM = """You produce a new piece of content that follows a \
given schema as closely as possible, given only a title/topic. Follow the \
schema's components in order, and follow each component's attributes \
literally. Do not pad with filler; if you don't have a real fact for a \
slot, write a plausible placeholder rather than vague language."""

GENERATION_USER_TEMPLATE = """Schema to follow:
{schema_block}

Write a new example titled "{title}" that follows this schema component by \
component. Match the rough length and register of typical examples in this \
domain. Return plain text only (no JSON, no markdown headers)."""


COMPARISON_SYSTEM = """You are revising a Components/Attributes/Relationships \
schema by contrasting an AI-generated example (built from the CURRENT \
schema) against a real, human-authored example on the same topic/title. \
Find concrete gaps: places where the schema's attributes were too vague to \
produce a convincing instance, or where the real example does something \
structurally important that the schema doesn't mention at all. Then \
produce an IMPROVED schema that closes those gaps -- tightened attributes, \
new relationships, or new components, as warranted. Keep everything else \
unchanged. Do not remove components unless they are genuinely redundant."""

COMPARISON_USER_TEMPLATE = """CURRENT SCHEMA:
{schema_block}

AI-GENERATED EXAMPLE (built from the schema above):
---
{generated_text}
---

REAL EXAMPLE (same title/topic, human-authored):
---
{real_text}
---

Compare them and produce an improved schema.

Return a JSON object shaped like:
{{
  "comparison_notes": "2-5 sentences on concrete gaps you found",
  "components": [
    {{
      "name": "Component name",
      "attributes": ["..."],
      "relationship_to_next": "..."
    }},
    ...
  ],
  "notes": "carry over or update the schema-level notes field"
}}"""


def render_examples_block(examples: List[Example], max_chars: int = 1200) -> str:
    """Render a list of examples as numbered id/title/text blocks for a prompt.

    Truncates very long texts so the clustering/abstraction prompts stay a
    reasonable size when you have many long source documents; the model
    only needs enough of each example to recognize its structural shape.
    """
    blocks = []
    for ex in examples:
        text = ex.text.strip()
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + " [...truncated...]"
        blocks.append(f"### id: {ex.id}\nTitle: {ex.title}\n{text}")
    return "\n\n".join(blocks)


def build_clustering_prompt(examples: List[Example]) -> str:
    return CLUSTERING_USER_TEMPLATE.format(
        n=len(examples),
        examples_block=render_examples_block(examples),
    )


def build_abstraction_prompt(cluster_name: str, rationale: str, examples: List[Example]) -> str:
    return ABSTRACTION_USER_TEMPLATE.format(
        cluster_name=cluster_name,
        rationale=rationale or "(none given)",
        examples_block=render_examples_block(examples, max_chars=2500),
    )


def build_generation_prompt(schema: Schema, title: str) -> str:
    return GENERATION_USER_TEMPLATE.format(
        schema_block=schema.as_prompt_block(),
        title=title,
    )


COVERAGE_SYSTEM = """You are an experienced editor checking whether a \
journalist's draft covers everything expected of its structural type, \
based on a schema derived from real published examples of that type. You \
are looking for missing or underdeveloped components -- the kind of gap \
an editor would flag before publication. Be specific and concrete: point \
to what is actually missing or weak, not generic praise or criticism. If \
a component IS present but doesn't fully meet its attributes, mark it \
"weak" rather than "present" or "missing", and explain exactly which \
attribute isn't met. Do not invent issues that aren't there -- if a \
component is genuinely well covered, say so plainly."""

COVERAGE_USER_TEMPLATE = """SCHEMA (cluster: "{cluster_name}"):
{schema_block}

DRAFT TO CHECK:
---
{draft_text}
---

For EVERY component in the schema, decide whether the draft has it, and \
how well it meets the component's attributes. Use status "present" \
(clearly there and meets the attributes), "weak" (present but missing one \
or more attributes, vague, or underdeveloped), or "missing" (not present \
at all).

Return a JSON object shaped like:
{{
  "items": [
    {{
      "component_name": "Component name (must match schema exactly)",
      "status": "present" | "weak" | "missing",
      "explanation": "1-3 sentences: what's there, what's missing, or what's weak, citing the relevant attribute(s)",
      "suggestion": "if weak or missing, a concrete, actionable suggestion for what to add or fix. Empty string if present."
    }},
    ...
  ],
  "overall_summary": "2-4 sentences: the single most important gap to fix before this draft is ready, and the overall coverage picture"
}}"""


def build_comparison_prompt(schema: Schema, generated_text: str, real_text: str) -> str:
    return COMPARISON_USER_TEMPLATE.format(
        schema_block=schema.as_prompt_block(),
        generated_text=generated_text,
        real_text=real_text,
    )


def build_coverage_prompt(schema: Schema, draft_text: str, cluster_name: str) -> str:
    return COVERAGE_USER_TEMPLATE.format(
        cluster_name=cluster_name,
        schema_block=schema.as_prompt_block(),
        draft_text=draft_text.strip(),
    )