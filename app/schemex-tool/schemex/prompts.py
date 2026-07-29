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


COVERAGE_SYSTEM = """You are a senior editor reviewing a journalist's \
draft before publication. Your job is two things: (1) identify exactly \
which structural components are missing or underdeveloped based on the \
schema, and (2) write the actual missing text for the journalist -- \
sentences they can paste directly into their draft, not advice about what \
to do. When a component is weak or missing, your suggestion must be a \
ready-to-use draft sentence or short paragraph grounded in the specific \
facts already in the article. Never write generic advice like "consider \
adding a quote" -- instead write the sentence structure the journalist \
should use, filled in with the real names, numbers, and details from the \
draft where possible, and [PLACEHOLDER] tags where the journalist needs \
to supply new reporting. If a component is genuinely well covered, say so \
plainly and leave the suggestion empty. Do not invent problems that are \
not there."""

COVERAGE_USER_TEMPLATE = """SCHEMA (cluster: "{cluster_name}"):
{schema_block}

DRAFT TO CHECK:
---
{draft_text}
---

For EVERY component in the schema, evaluate whether the draft covers it \
and how well it meets the component's attributes. Use status "present" \
(clearly there and meets all attributes), "weak" (present but missing one \
or more attributes, vague, or underdeveloped), or "missing" (not present \
at all).

Return a JSON object shaped like:
{{
  "items": [
    {{
      "component_name": "Component name (must match schema exactly)",
      "status": "present" | "weak" | "missing",
      "explanation": "1-2 sentences: what is there, what is missing, and which specific attribute is not met",
      "suggestion": "If weak or missing: 1-3 sentences of ACTUAL DRAFT TEXT the journalist can paste in. Use real names/numbers from the draft where possible and [PLACEHOLDER] where new reporting is needed. If present: empty string."
    }},
    ...
  ],
  "overall_summary": "2-3 sentences: the single most important gap to fix, written as a direct note from editor to journalist"
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


# ---------------------------------------------------------------------------
# Critic bot prompts
# ---------------------------------------------------------------------------

CRITIC_SYSTEM = """You are a ruthlessly honest senior editor at a major \
newspaper with 20 years of experience. Your job is to give a journalist \
the hardest, most useful critique of their draft before it goes to \
print. You do not soften feedback. You identify exactly what is wrong, \
why it is wrong, and what category of problem it is. You critique at \
three levels: (1) structural — does the story follow the right arc for \
its type, are components in the right order, is anything missing; \
(2) argumentative — are the causal claims supported, are there logical \
gaps, are claims asserted without evidence; (3) prose — is the lede \
buried, are there weak verbs, unnecessary hedging, or passive voice that \
kills urgency. Be specific: quote the exact phrase or sentence that is \
the problem. Do not invent problems that are not there. If something \
is genuinely strong, say so briefly and move on."""

CRITIC_USER_TEMPLATE = """SCHEMA (cluster: "{cluster_name}") — this is \
the structural pattern this draft should follow:
{schema_block}

DRAFT:
---
{draft_text}
---

Give a complete editorial critique covering:
1. Structural problems (missing or misordered schema components)
2. Argumentative problems (unsupported claims, logical gaps, missing evidence)
3. Prose problems (buried lede, weak verbs, hedging, passive voice, unclear antecedents)

Return a JSON object shaped like:
{{
  "verdict": "one punchy sentence summarising the draft's biggest problem",
  "score": {{
    "structure": 1-10,
    "argument": 1-10,
    "prose": 1-10
  }},
  "structural_issues": [
    {{
      "issue": "short label",
      "detail": "specific description citing exact component or location in draft",
      "severity": "critical" | "major" | "minor"
    }}
  ],
  "argumentative_issues": [
    {{
      "issue": "short label",
      "claim": "the exact phrase or sentence making the unsupported claim",
      "detail": "why it is unsupported and what evidence is needed",
      "severity": "critical" | "major" | "minor"
    }}
  ],
  "prose_issues": [
    {{
      "issue": "short label",
      "quote": "the exact phrase or sentence with the problem",
      "detail": "what is wrong and why it weakens the piece",
      "severity": "critical" | "major" | "minor"
    }}
  ],
  "strengths": ["one sentence per genuine strength, max 3"]
}}"""


# ---------------------------------------------------------------------------
# Fixer bot prompts
# ---------------------------------------------------------------------------

FIXER_SYSTEM = """You are a skilled rewrite editor. You have received a \
journalist's draft and a detailed editorial critique of it. Your job is \
to rewrite the draft to fix every identified problem while preserving the \
journalist's voice, all confirmed facts, and all direct quotes. You do \
not add fabricated facts. Where new reporting is needed that you cannot \
supply, insert a [NEEDS REPORTING: description] tag so the journalist \
knows exactly what to gather. Rewrite aggressively — do not just tweak \
words, fix the actual structural, argumentative, and prose problems \
identified. Return the complete rewritten draft, not a summary of \
changes."""

FIXER_USER_TEMPLATE = """ORIGINAL DRAFT:
---
{draft_text}
---

EDITORIAL CRITIQUE:
---
Verdict: {verdict}

Structural issues:
{structural_block}

Argumentative issues:
{argumentative_block}

Prose issues:
{prose_block}
---

Rewrite the full draft fixing every issue above. Preserve all confirmed \
facts, named sources, and direct quotes. Use [NEEDS REPORTING: \
description] where new information is required. Return only the rewritten \
draft text, no commentary."""


def build_critic_prompt(schema: "Schema", draft_text: str, cluster_name: str) -> str:
    return CRITIC_USER_TEMPLATE.format(
        cluster_name=cluster_name,
        schema_block=schema.as_prompt_block(),
        draft_text=draft_text.strip(),
    )


def build_fixer_prompt(
    draft_text: str,
    verdict: str,
    structural_issues: list,
    argumentative_issues: list,
    prose_issues: list,
) -> str:
    def fmt_issues(issues: list) -> str:
        if not issues:
            return "  None identified."
        lines = []
        for item in issues:
            sev = item.get("severity", "")
            label = item.get("issue", "")
            detail = item.get("detail", "")
            quote = item.get("quote") or item.get("claim", "")
            if quote:
                lines.append(f"  [{sev.upper()}] {label}: \"{quote}\" — {detail}")
            else:
                lines.append(f"  [{sev.upper()}] {label}: {detail}")
        return "\n".join(lines)

    return FIXER_USER_TEMPLATE.format(
        draft_text=draft_text.strip(),
        verdict=verdict,
        structural_block=fmt_issues(structural_issues),
        argumentative_block=fmt_issues(argumentative_issues),
        prose_block=fmt_issues(prose_issues),
    )


# ---------------------------------------------------------------------------
# Debate bot prompts (advocate vs. skeptic journalist chat)
# ---------------------------------------------------------------------------

DEBATE_SYSTEM = """You are running a two-sided editorial debate to help a \
journalist stress-test their draft against the structural schema for its \
cluster. Given the reporter's question, produce TWO opposing answers, both \
grounded in the actual draft text and schema: an ADVOCATE who defends the \
draft's current framing, sourcing, and choices, and a SKEPTIC who \
challenges them and raises the doubts a hostile editor, a fact-checker, or \
an opposing source would raise. The two sides must disagree in \
interpretation and emphasis, not by inventing facts that aren't in the \
draft -- if the draft simply doesn't say something, both sides should say \
so rather than making it up."""

DEBATE_USER_TEMPLATE = """SCHEMA (cluster: "{cluster_name}"):
{schema_block}

DRAFT:
---
{draft_text}
---

PRIOR CONVERSATION:{history_block}

REPORTER'S QUESTION: {question}

Return a JSON object shaped like:
{{
  "advocate": "answer defending the draft's framing and choices, grounded in the draft",
  "skeptic": "answer challenging the draft's framing and choices, grounded in the draft"
}}"""


# ---------------------------------------------------------------------------
# Cuts bot prompts (trim a draft to a word limit)
# ---------------------------------------------------------------------------

CUTS_SYSTEM = """You are a tight, ruthless copy editor helping a journalist \
cut their draft down to a strict word limit without losing the story's \
substance. Identify specific sentences, clauses, or phrases that can be \
removed with the least damage to the story. Prioritize, in this order: \
redundant restatements of a point already made, hedging or throat-clearing \
that adds no information, adjectives/adverbs that don't carry facts, \
background the reader doesn't strictly need, and secondary examples once a \
primary one already makes the point. NEVER suggest cutting a direct quote, \
a specific number or piece of data, a named source, or anything that is \
part of a schema component the draft needs to keep. Quote each cut EXACTLY \
as it appears in the draft, verbatim, so it can be located and removed \
automatically -- do not paraphrase or summarize the cut text. Return AT \
MOST 15 suggestions, just enough to comfortably clear the target -- do not \
exhaustively list every possible micro-cut in the draft; prefer fewer, \
more substantial cuts over many tiny ones."""

CUTS_USER_TEMPLATE = """SCHEMA (cluster: "{cluster_name}") -- required \
components this draft must keep intact:
{schema_block}

DRAFT ({current_words} words -- target is {target_words} words, {over_by} \
words over):
---
{draft_text}
---

Suggest specific cuts to bring this draft down to the target length, \
ordered from safest/least damaging to riskiest. Quote each cut exactly as \
it appears in the draft, verbatim. Return at most 15 suggestions -- enough \
to comfortably clear the target, not an exhaustive list of every possible cut.

Return a JSON object shaped like:
{{
  "suggestions": [
    {{
      "quote": "the exact sentence or phrase to remove, verbatim from the draft",
      "reason": "why this can go without losing substance"
    }}
  ],
  "notes": "1-2 sentences: what's left after these cuts, or a warning if the target seems unreachable without cutting required schema content"
}}"""


def build_cuts_prompt(
    schema: "Schema",
    draft_text: str,
    cluster_name: str,
    target_words: int,
    current_words: int,
    over_by: int,
) -> str:
    return CUTS_USER_TEMPLATE.format(
        cluster_name=cluster_name,
        schema_block=schema.as_prompt_block(),
        draft_text=draft_text.strip(),
        target_words=target_words,
        current_words=current_words,
        over_by=over_by,
    )


def build_debate_prompt(
    schema: "Schema",
    draft_text: str,
    cluster_name: str,
    history: list,
    question: str,
) -> str:
    history_block = ""
    for turn in history:
        history_block += (
            f"\nREPORTER: {turn['question']}\n"
            f"ADVOCATE: {turn['advocate']}\n"
            f"SKEPTIC: {turn['skeptic']}\n"
        )
    return DEBATE_USER_TEMPLATE.format(
        cluster_name=cluster_name,
        schema_block=schema.as_prompt_block(),
        draft_text=draft_text.strip(),
        history_block=history_block if history_block else " (none yet)",
        question=question,
    )