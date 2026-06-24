"""Command-line interface for schemex.

Usage:
    schemex run --input examples.json --output out/
    schemex run --input examples.json --output out/ --mode interactive
    schemex run --input examples.json --output out/ --iterations 2 --seed 7

Run `schemex run --help` for all options.
"""
from __future__ import annotations

import argparse
import sys

from .io_utils import load_examples
from .llm import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, ClaudeClient, LLMError
from .pipeline import run_pipeline


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

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())