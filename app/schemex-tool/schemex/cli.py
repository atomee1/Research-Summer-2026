"""Command-line interface for schemex.

Usage:
    schemex run --input examples.json --output out/
    schemex run --input examples.json --output out/ --mode interactive
    schemex run --input examples.json --output out/ --iterations 2 --seed 7

Run `schemex run --help` for all options.
"""
from __future__ import annotations

import argparse
import os
import sys

from .io_utils import (
    RunState,
    inject_coverage_into_graph,
    inject_critique_into_graph,
    load_examples,
    write_coverage_html,
    write_coverage_report,
    write_critique_report,
)
from .llm import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, ClaudeClient, LLMError
from .pipeline import pick_best_cluster, run_coverage_check, run_critique, run_fixer, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schemex",
        description="Discover actionable schemas from a set of examples "
                     "(clustering -> abstraction -> refinement).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the full pipeline on a set of examples.")
    run.add_argument(
        "--input", "-i", required=True,
        help="Path to a JSON file of examples, or a directory of .txt files.",
    )
    run.add_argument(
        "--output", "-o", default="schemex_out",
        help="Directory to write state.json and report.md into (default: ./schemex_out).",
    )
    run.add_argument(
        "--mode", choices=["automated", "interactive"], default="automated",
        help="automated: one-shot run with no prompts (default). "
             "interactive: pause for review after clustering, abstraction, "
             "and each refinement iteration.",
    )
    run.add_argument(
        "--iterations", type=int, default=1,
        help="Number of apply-and-test refinement rounds per cluster (default: 1).",
    )
    run.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for choosing which example to contrast against "
             "during refinement, for reproducible runs.",
    )
    run.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL}; or set SCHEMEX_MODEL). "
             "See https://docs.claude.com for current model names.",
    )
    run.add_argument(
        "--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
        help=f"Max tokens per model response (default: {DEFAULT_MAX_TOKENS}).",
    )
    run.add_argument(
        "--api-key", default=None,
        help="Anthropic API key. Defaults to the ANTHROPIC_API_KEY env var.",
    )
    run.add_argument(
        "--verbose", action="store_true",
        help="Print full prompts and responses for every model call.",
    )

    check = sub.add_parser(
        "check",
        help="Check a journalist's draft against a schema from a previous "
             "run and report missing or weak components.",
    )
    check.add_argument(
        "--draft", "-d", required=True,
        help="Path to a plain-text draft article to check.",
    )
    check.add_argument(
        "--state", "-s", required=True,
        help="Path to a schemex output directory containing state.json "
             "(from a previous `schemex run`).",
    )
    check.add_argument(
        "--cluster", default=None,
        help="Cluster id to check against. If omitted, the model picks "
             "the best-matching cluster automatically.",
    )
    check.add_argument(
        "--output", "-o", default=None,
        help="Directory to write the coverage report into "
             "(default: the --state directory).",
    )
    check.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL}; or set SCHEMEX_MODEL).",
    )
    check.add_argument(
        "--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
        help=f"Max tokens per model response (default: {DEFAULT_MAX_TOKENS}).",
    )
    check.add_argument(
        "--api-key", default=None,
        help="Anthropic API key. Defaults to the ANTHROPIC_API_KEY env var.",
    )
    check.add_argument(
        "--verbose", action="store_true",
        help="Print full prompts and responses for every model call.",
    )

    critique = sub.add_parser(
        "critique",
        help="Run the critic bot on a draft for deep editorial feedback, "
             "then optionally run the fixer bot to produce a rewritten draft.",
    )
    critique.add_argument("--draft", "-d", required=True,
        help="Path to the draft text file to critique.")
    critique.add_argument("--state", "-s", required=True,
        help="Path to schemex output directory containing state.json.")
    critique.add_argument("--cluster", default=None,
        help="Cluster id to check against (auto-detected if omitted).")
    critique.add_argument("--fix", action="store_true",
        help="After critiquing, run the fixer bot to produce a rewritten draft.")
    critique.add_argument("--output", "-o", default=None,
        help="Directory to write reports into (default: --state directory).")
    critique.add_argument("--model", default=DEFAULT_MODEL)
    critique.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    critique.add_argument("--api-key", default=None)
    critique.add_argument("--verbose", action="store_true")

    serve = sub.add_parser(
        "serve",
        help="Serve the schema graph with a live fixer, critic bot, coverage "
             "check, and advocate/skeptic debate chat in the browser.",
    )
    serve.add_argument("--state", "-s", required=True,
        help="Path to schemex output directory containing state.json.")
    serve.add_argument("--port", "-p", type=int, default=8000,
        help="Port to serve on (default: 8000).")
    serve.add_argument("--model", default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL}; or set SCHEMEX_MODEL).")
    serve.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    serve.add_argument("--api-key", default=None,
        help="Anthropic API key. Defaults to the ANTHROPIC_API_KEY env var. "
             "Only needed once you click Critique/Coverage/Fix/Ask in the browser.")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            examples = load_examples(args.input)
        except (OSError, ValueError) as exc:
            print(f"Error loading examples: {exc}", file=sys.stderr)
            return 1

        if len(examples) < 2:
            print("Need at least 2 examples to find a pattern.", file=sys.stderr)
            return 1

        try:
            client = ClaudeClient(
                model=args.model,
                max_tokens=args.max_tokens,
                api_key=args.api_key,
                verbose=args.verbose,
            )
        except LLMError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        run_pipeline(
            client,
            examples,
            output_dir=args.output,
            iterations=args.iterations,
            interactive=(args.mode == "interactive"),
            seed=args.seed,
        )
        return 0

    if args.command == "check":
        if not os.path.exists(args.draft):
            print(f"Error: draft file not found: {args.draft}", file=sys.stderr)
            return 1
        with open(args.draft, "r", encoding="utf-8") as f:
            draft_text = f.read()
        if not draft_text.strip():
            print("Error: draft file is empty.", file=sys.stderr)
            return 1

        state = RunState.load(args.state)
        if not state.clusters or not state.schemas:
            print(
                f"Error: no clusters/schemas found in {args.state}. "
                f"Run `schemex run` first to produce a state.json there.",
                file=sys.stderr,
            )
            return 1

        try:
            client = ClaudeClient(
                model=args.model,
                max_tokens=args.max_tokens,
                api_key=args.api_key,
                verbose=args.verbose,
            )
        except LLMError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        if args.cluster:
            cluster = next((c for c in state.clusters if c.id == args.cluster), None)
            if cluster is None:
                print(f"Error: no cluster with id '{args.cluster}' in {args.state}. "
                      f"Available ids: {', '.join(c.id for c in state.clusters)}",
                      file=sys.stderr)
                return 1
        else:
            cluster = pick_best_cluster(client, draft_text, state.clusters)
            print(f"[coverage] auto-matched draft to cluster '{cluster.name}' "
                  f"({cluster.id})")

        schema = state.schemas.get(cluster.id)
        if schema is None:
            print(f"Error: cluster '{cluster.id}' has no schema in {args.state}.",
                  file=sys.stderr)
            return 1

        report = run_coverage_check(client, args.draft, draft_text, schema, cluster)

        output_dir = args.output or args.state
        md_path   = write_coverage_report(report, output_dir)
        html_path = write_coverage_html(report, output_dir)

        # Inject coverage colours into graph.html if it exists
        graph_path = os.path.join(output_dir, "graph.html")
        graph_updated = inject_coverage_into_graph(report, graph_path)

        print(f"\nCoverage report  -> {md_path}")
        print(f"Visual report    -> {html_path}")
        if graph_updated:
            print(f"Graph updated    -> {graph_path}  (node colours now reflect coverage)")
        else:
            print("Note: graph.html not found in output dir — run `schemex run` first to generate it.")
        return 0

    if args.command == "critique":
        if not os.path.exists(args.draft):
            print(f"Error: draft file not found: {args.draft}", file=sys.stderr)
            return 1
        with open(args.draft, "r", encoding="utf-8") as f:
            draft_text = f.read()
        if not draft_text.strip():
            print("Error: draft file is empty.", file=sys.stderr)
            return 1

        state = RunState.load(args.state)
        if not state.clusters or not state.schemas:
            print(f"Error: run `schemex run` first.", file=sys.stderr)
            return 1

        try:
            client = ClaudeClient(
                model=args.model,
                max_tokens=args.max_tokens,
                api_key=args.api_key,
                verbose=args.verbose,
            )
        except LLMError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        if args.cluster:
            cluster = next((c for c in state.clusters if c.id == args.cluster), None)
            if cluster is None:
                print(f"Error: cluster '{args.cluster}' not found.", file=sys.stderr)
                return 1
        else:
            cluster = pick_best_cluster(client, draft_text, state.clusters)
            print(f"[critique] auto-matched to cluster '{cluster.name}'")

        schema = state.schemas.get(cluster.id)
        if schema is None:
            print(f"Error: no schema for cluster '{cluster.id}'.", file=sys.stderr)
            return 1

        critique = run_critique(client, args.draft, draft_text, schema, cluster)

        if args.fix:
            fixed = run_fixer(client, draft_text, critique)
            critique.fixed_draft = fixed

        output_dir = args.output or args.state
        md_path, html_path = write_critique_report(critique, output_dir)

        graph_path    = os.path.join(output_dir, "graph.html")
        graph_updated = inject_critique_into_graph(critique, graph_path)

        print(f"\nCritique report  -> {md_path}")
        print(f"Visual report    -> {html_path}")
        if graph_updated:
            print(f"Graph updated    -> {graph_path}  (nodes coloured by issue severity)")
        else:
            print("Note: graph.html not found — run `schemex run` first.")
        if critique.fixed_draft:
            print(f"Fixed draft included in both reports.")
        return 0

    if args.command == "serve":
        from .server import run_server

        return run_server(
            state_dir=args.state,
            port=args.port,
            model=args.model,
            max_tokens=args.max_tokens,
            api_key=args.api_key,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())