"""Data models shared across pipeline stages.

Kept deliberately as plain dataclasses with to_dict/from_dict helpers
rather than a heavier framework, since the whole point of this tool is
to be easy to read and modify.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Example:
    """One input item (an article, abstract, transcript, recipe, etc.)."""

    id: str
    title: str
    text: str
    source_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Example":
        return cls(
            id=d["id"],
            title=d.get("title", ""),
            text=d.get("text", ""),
            source_url=d.get("source_url"),
            metadata=d.get("metadata", {}) or {},
        )


@dataclass
class Cluster:
    """A latent-structure grouping of example ids produced by Stage 1."""

    id: str
    name: str
    member_ids: List[str]
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Cluster":
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            member_ids=list(d.get("member_ids", [])),
            rationale=d.get("rationale", ""),
        )


@dataclass
class SchemaComponent:
    """One slot in a schema (e.g. 'Findings'), with content norms and the
    causal/structural link to the component that follows it."""

    name: str
    attributes: List[str] = field(default_factory=list)
    relationship_to_next: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SchemaComponent":
        return cls(
            name=d["name"],
            attributes=list(d.get("attributes", [])),
            relationship_to_next=d.get("relationship_to_next", ""),
        )


@dataclass
class Schema:
    """The Components / Attributes / Relationships schema for one cluster.

    `version` increments every time Stage 3 (refinement) iterates it, so
    the full revision history is preserved rather than overwritten.
    """

    cluster_id: str
    version: int
    components: List[SchemaComponent]
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "version": self.version,
            "components": [c.to_dict() for c in self.components],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Schema":
        return cls(
            cluster_id=d["cluster_id"],
            version=d.get("version", 1),
            components=[SchemaComponent.from_dict(c) for c in d.get("components", [])],
            notes=d.get("notes", ""),
        )

    def as_prompt_block(self) -> str:
        """Render the schema as readable text for inclusion in a prompt."""
        lines = []
        for i, c in enumerate(self.components):
            lines.append(f"{i + 1}. {c.name}")
            for a in c.attributes:
                lines.append(f"   - {a}")
            if c.relationship_to_next:
                lines.append(f"   -> next: {c.relationship_to_next}")
        return "\n".join(lines)


@dataclass
class RefinementRound:
    """Record of one apply-and-test iteration for a single cluster."""

    cluster_id: str
    iteration: int
    example_id: str
    generated_text: str
    comparison_notes: str
    schema_before: Schema
    schema_after: Schema

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "iteration": self.iteration,
            "example_id": self.example_id,
            "generated_text": self.generated_text,
            "comparison_notes": self.comparison_notes,
            "schema_before": self.schema_before.to_dict(),
            "schema_after": self.schema_after.to_dict(),
        }