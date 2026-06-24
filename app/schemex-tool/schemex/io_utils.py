"""Input loading and output saving helpers."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .models import Cluster, Example, RefinementRound, Schema


def load_examples(path: str) -> List[Example]:
    """Load examples from either:

    - a single JSON file containing a list of objects with at least
      "id", "title", "text" (see examples/wikinews_sample.json), or
    - a directory of .txt files, where each file's name (minus extension)
      becomes the id and title, and its contents become the text.
    """
    if os.path.isdir(path):
        examples = []
        for fname in sorted(os.listdir(path)):
            if not fname.lower().endswith(".txt"):
                continue
            full = os.path.join(path, fname)
            with open(full, "r", encoding="utf-8") as f:
                text = f.read()
            ex_id = os.path.splitext(fname)[0]
            examples.append(Example(id=ex_id, title=ex_id.replace("_", " "), text=text))
        if not examples:
            raise ValueError(f"No .txt files found in directory: {path}")
        return examples

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array of examples in {path}, got {type(data).__name__}"
        )
    return [Example.from_dict(d) for d in data]


def examples_by_id(examples: List[Example]) -> Dict[str, Example]:
    return {ex.id: ex for ex in examples}


class RunState:
    """Accumulates and persists the full pipeline run so intermediate
    results survive a crash and so --mode interactive can resume."""

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.clusters: List[Cluster] = []
        self.schemas: Dict[str, Schema] = {}  # cluster_id -> latest Schema
        self.refinement_history: List[RefinementRound] = []
        os.makedirs(output_dir, exist_ok=True)

    def save(self) -> None:
        path = os.path.join(self.output_dir, "state.json")
        payload = {
            "clusters": [c.to_dict() for c in self.clusters],
            "schemas": {cid: s.to_dict() for cid, s in self.schemas.items()},
            "refinement_history": [r.to_dict() for r in self.refinement_history],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    @classmethod
    def load(cls, output_dir: str) -> "RunState":
        state = cls(output_dir)
        path = os.path.join(output_dir, "state.json")
        if not os.path.exists(path):
            return state
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        state.clusters = [Cluster.from_dict(c) for c in payload.get("clusters", [])]
        state.schemas = {
            cid: Schema.from_dict(s) for cid, s in payload.get("schemas", {}).items()
        }
        # Refinement history is informational only; not reconstructed into
        # objects on load since it's never mutated, only appended to and
        # re-saved within a single run.
        return state

    def write_report(self) -> str:
        """Write a human-readable Markdown summary of the final schemas."""
        lines = ["# Schemex run report\n"]
        for cluster in self.clusters:
            schema = self.schemas.get(cluster.id)
            lines.append(f"## Cluster: {cluster.name} (`{cluster.id}`)\n")
            lines.append(f"**Members:** {', '.join(cluster.member_ids)}\n")
            lines.append(f"**Rationale:** {cluster.rationale}\n")
            if schema:
                lines.append(f"**Schema (v{schema.version}):**\n")
                for comp in schema.components:
                    lines.append(f"- **{comp.name}**")
                    for attr in comp.attributes:
                        lines.append(f"  - {attr}")
                    if comp.relationship_to_next:
                        lines.append(f"  - *-> next:* {comp.relationship_to_next}")
                if schema.notes:
                    lines.append(f"\n_Notes: {schema.notes}_")
            lines.append("\n---\n")

        report = "\n".join(lines)
        path = os.path.join(self.output_dir, "report.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        return path