"""Pipeline stages: Clustering -> Abstraction -> Refinement -> Graph Report

Each stage is a plain function so it's easy to call from a script, a
notebook, or the CLI in cli.py. Interactivity is handled by passing
`interactive=True`, which pauses at decision points using plain
input() prompts -- no extra dependencies, easy to swap for a real UI
later if you want one.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from .io_utils import RunState, examples_by_id
from .llm import ClaudeClient
from .models import Cluster, Example, RefinementRound, Schema, SchemaComponent
from .prompts import (
    ABSTRACTION_SYSTEM,
    CLUSTERING_SYSTEM,
    COMPARISON_SYSTEM,
    GENERATION_SYSTEM,
    build_abstraction_prompt,
    build_clustering_prompt,
    build_comparison_prompt,
    build_generation_prompt,
)


# ---------------------------------------------------------------------------
# Stage 1: Clustering
# ---------------------------------------------------------------------------

def run_clustering(
    client: ClaudeClient,
    examples: List[Example],
    interactive: bool = False,
) -> List[Cluster]:
    print(f"[clustering] sending {len(examples)} examples to {client.model} ...")
    prompt = build_clustering_prompt(examples)
    raw_clusters = client.complete_json(CLUSTERING_SYSTEM, prompt)
    clusters = [Cluster.from_dict(c) for c in raw_clusters]

    _validate_cluster_coverage(clusters, examples)

    if interactive:
        clusters = _interactive_review_clusters(clusters, examples)

    for c in clusters:
        print(f"  - {c.name} ({len(c.member_ids)} examples): {c.rationale}")
    return clusters


def _validate_cluster_coverage(clusters: List[Cluster], examples: List[Example]) -> None:
    all_ids = {ex.id for ex in examples}
    seen = set()
    for c in clusters:
        seen.update(c.member_ids)
    missing = all_ids - seen
    if missing:
        # Don't crash the run over this -- drop them into a catch-all
        # cluster so nothing silently disappears, and flag it loudly.
        print(
            f"  [warning] {len(missing)} example(s) were not assigned to any "
            f"cluster by the model: {sorted(missing)}. Adding an 'unclustered' "
            f"bucket."
        )
        clusters.append(
            Cluster(
                id="unclustered",
                name="Unclustered",
                member_ids=sorted(missing),
                rationale="Examples the model did not assign to a cluster.",
            )
        )


def _interactive_review_clusters(
    clusters: List[Cluster], examples: List[Example]
) -> List[Cluster]:
    by_id = examples_by_id(examples)
    print("\n=== Stage 1: Clustering (interactive review) ===")
    while True:
        for c in clusters:
            titles = [by_id[m].title for m in c.member_ids if m in by_id]
            print(f"\n[{c.id}] {c.name}")
            print(f"  rationale: {c.rationale}")
            for mid, title in zip(c.member_ids, titles):
                print(f"   - {mid}: {title}")

        choice = input(
            "\nAccept clusters as-is? [y]es / [m]erge two clusters / "
            "[r]ename a cluster / [d]rop an example from its cluster: "
        ).strip().lower()

        if choice in ("", "y", "yes"):
            return clusters
        if choice in ("m", "merge"):
            a = input("  cluster id to merge FROM: ").strip()
            b = input("  cluster id to merge INTO: ").strip()
            clusters = _merge_clusters(clusters, a, b)
        elif choice in ("r", "rename"):
            cid = input("  cluster id to rename: ").strip()
            new_name = input("  new name: ").strip()
            for c in clusters:
                if c.id == cid:
                    c.name = new_name
        elif choice in ("d", "drop"):
            ex_id = input("  example id to drop: ").strip()
            cid = input("  from cluster id: ").strip()
            for c in clusters:
                if c.id == cid and ex_id in c.member_ids:
                    c.member_ids.remove(ex_id)
                    print(f"  dropped {ex_id} from {cid}. It now belongs to no "
                          f"cluster -- re-add it manually if needed.")
        else:
            print("  not understood, try again.")


def _merge_clusters(clusters: List[Cluster], from_id: str, into_id: str) -> List[Cluster]:
    src = next((c for c in clusters if c.id == from_id), None)
    dst = next((c for c in clusters if c.id == into_id), None)
    if not src or not dst:
        print("  could not find one of those cluster ids, no change made.")
        return clusters
    dst.member_ids = list(dict.fromkeys(dst.member_ids + src.member_ids))
    dst.rationale = (dst.rationale + " Merged with: " + src.rationale).strip()
    return [c for c in clusters if c.id != from_id]


# ---------------------------------------------------------------------------
# Stage 2: Abstraction
# ---------------------------------------------------------------------------

def run_abstraction(
    client: ClaudeClient,
    clusters: List[Cluster],
    examples: List[Example],
    interactive: bool = False,
) -> Dict[str, Schema]:
    by_id = examples_by_id(examples)
    schemas: Dict[str, Schema] = {}

    for cluster in clusters:
        members = [by_id[mid] for mid in cluster.member_ids if mid in by_id]
        if not members:
            continue
        print(f"[abstraction] deriving schema for cluster '{cluster.name}' "
              f"({len(members)} examples) ...")
        prompt = build_abstraction_prompt(cluster.name, cluster.rationale, members)
        raw = client.complete_json(ABSTRACTION_SYSTEM, prompt)
        schema = Schema(
            cluster_id=cluster.id,
            version=1,
            components=[SchemaComponent.from_dict(c) for c in raw.get("components", [])],
            notes=raw.get("notes", ""),
        )

        if interactive:
            schema = _interactive_review_schema(cluster, schema)

        schemas[cluster.id] = schema
        print(f"  -> {len(schema.components)} components: "
              f"{', '.join(c.name for c in schema.components)}")

    return schemas


def _interactive_review_schema(cluster: Cluster, schema: Schema) -> Schema:
    print(f"\n=== Stage 2: Abstraction (interactive review) -- {cluster.name} ===")
    print(schema.as_prompt_block())
    if schema.notes:
        print(f"\nNotes: {schema.notes}")

    while True:
        choice = input(
            "\nAccept this schema? [y]es / [e]dit a component's attributes "
            "in a text editor-style prompt: "
        ).strip().lower()
        if choice in ("", "y", "yes"):
            return schema
        if choice in ("e", "edit"):
            name = input("  component name to edit: ").strip()
            comp = next((c for c in schema.components if c.name == name), None)
            if not comp:
                print("  no component with that name.")
                continue
            print(f"  current attributes for {comp.name}:")
            for a in comp.attributes:
                print(f"   - {a}")
            print("  enter new attributes one per line, blank line to finish:")
            new_attrs = []
            while True:
                line = input("   > ").strip()
                if not line:
                    break
                new_attrs.append(line)
            if new_attrs:
                comp.attributes = new_attrs
        else:
            print("  not understood, try again.")


# ---------------------------------------------------------------------------
# Stage 3: Refinement via contrasting examples
# ---------------------------------------------------------------------------

def run_refinement(
    client: ClaudeClient,
    clusters: List[Cluster],
    examples: List[Example],
    schemas: Dict[str, Schema],
    iterations: int = 1,
    interactive: bool = False,
    seed: Optional[int] = None,
) -> List[RefinementRound]:
    rng = random.Random(seed)
    by_id = examples_by_id(examples)
    history: List[RefinementRound] = []

    for cluster in clusters:
        schema = schemas.get(cluster.id)
        if schema is None or not cluster.member_ids:
            continue

        member_pool = [by_id[m] for m in cluster.member_ids if m in by_id]
        if not member_pool:
            continue

        for i in range(1, iterations + 1):
            real_example = rng.choice(member_pool)
            print(f"[refinement] cluster '{cluster.name}' iteration {i}: "
                  f"generating from schema v{schema.version} using title "
                  f"'{real_example.title}' ...")

            gen_prompt = build_generation_prompt(schema, real_example.title)
            generated_text = client.complete(GENERATION_SYSTEM, gen_prompt)

            cmp_prompt = build_comparison_prompt(schema, generated_text, real_example.text)
            raw = client.complete_json(COMPARISON_SYSTEM, cmp_prompt)

            new_schema = Schema(
                cluster_id=cluster.id,
                version=schema.version + 1,
                components=[SchemaComponent.from_dict(c) for c in raw.get("components", [])],
                notes=raw.get("notes", schema.notes),
            )
            comparison_notes = raw.get("comparison_notes", "")

            round_record = RefinementRound(
                cluster_id=cluster.id,
                iteration=i,
                example_id=real_example.id,
                generated_text=generated_text,
                comparison_notes=comparison_notes,
                schema_before=schema,
                schema_after=new_schema,
            )

            if interactive:
                accept = _interactive_review_refinement(
                    cluster, real_example, generated_text, comparison_notes,
                    schema, new_schema,
                )
            else:
                accept = True

            history.append(round_record)
            if accept:
                schema = new_schema
                schemas[cluster.id] = schema
            else:
                print("  [kept previous schema version, no change applied]")

    return history


def _interactive_review_refinement(
    cluster: Cluster,
    real_example: Example,
    generated_text: str,
    comparison_notes: str,
    schema_before: Schema,
    schema_after: Schema,
) -> bool:
    print(f"\n=== Stage 3: Refinement (interactive review) -- {cluster.name} ===")
    print(f"\nReal example used for contrast: {real_example.title} ({real_example.id})")
    print("\n--- AI-generated (schema v{}) ---\n{}".format(schema_before.version, generated_text[:1500]))
    print("\n--- Real example ---\n{}".format(real_example.text[:1500]))
    print(f"\n--- Comparison notes ---\n{comparison_notes}")
    print(f"\n--- Proposed schema v{schema_after.version} ---\n{schema_after.as_prompt_block()}")

    choice = input(
        "\nAccept the new schema version? [y]es / [n]o, keep previous: "
    ).strip().lower()
    return choice in ("", "y", "yes")


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    client: ClaudeClient,
    examples: List[Example],
    output_dir: str,
    iterations: int = 1,
    interactive: bool = False,
    seed: Optional[int] = None,
) -> RunState:
    state = RunState(output_dir)

    state.clusters = run_clustering(client, examples, interactive=interactive)
    state.save()

    state.schemas = run_abstraction(
        client, state.clusters, examples, interactive=interactive
    )
    state.save()

    state.refinement_history = run_refinement(
        client,
        state.clusters,
        examples,
        state.schemas,
        iterations=iterations,
        interactive=interactive,
        seed=seed,
    )
    state.save()

    report_path = state.write_report()
    graph_path = state.write_graph_html()
    print(f"\nDone. Report written to {report_path}")
    print(f"Graph written to  {graph_path}")
    print(f"Full state written to {output_dir}/state.json")
    return state