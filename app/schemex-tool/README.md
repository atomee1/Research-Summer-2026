# Schemex

A small, hackable command-line implementation of the **Schemex** workflow:
discovering actionable schemas from a set of examples through iterative
clustering, abstraction, and refinement.

Based on:

> Sitong Wang & Lydia B. Chilton, "Schemex: Discovering Design Patterns from
> Examples through Iterative Abstraction and Refinement," arXiv:2502.15105,
> 2025.

This is an independent, from-scratch reimplementation for personal/research
use -- not the original authors' code.

## What it does

Give it a pile of examples (CHI abstracts, news articles, recipes, sales
emails, whatever) and it will:

1. **Cluster** them by *latent structure* -- how they're built (lede, then
   quote, then reaction; or finding, then method, then implication) -- not
   by topic.
2. **Abstract** a schema for each cluster: a list of **Components** (the
   recurring slots), each with **Attributes** (content norms -- what a good
   instance of that slot actually contains) and a **Relationship** to the
   component that follows it (how one slot causally/structurally leads to
   the next).
3. **Refine** each schema by generating a new example from it (given just a
   title), contrasting that generated example against a real one on the
   same topic, and asking the model to tighten the schema based on the
   concrete gaps it finds. Repeat for as many iterations as you like.

The output is a `report.md` (human-readable schemas per cluster) and a
`state.json` (full machine-readable history, including every generated
example and every schema revision, so you can audit how the schema
evolved).

## Why "latent structure, not topic"

Two examples about completely different subjects can be built the same way
(an M&A rejection and a regulatory-delay announcement might both be:
*Decision -> Actor -> prior pressure -> quoted justification -> reactions
from both sides*). Two examples on the very same subject can be built
totally differently (a financial report and an op-ed about the same
company). Schemex clusters on the former axis. The prompts in
`schemex/prompts.py` say this explicitly, since it's the part LLMs default
away from if you don't ask for it directly.

## Install

```bash
git clone <this-repo>
cd schemex
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

(Or just `pip install -r requirements.txt` and run with
`python -m schemex run ...` instead of installing the `schemex` entry
point.)

## Quickstart

A 22-example sample dataset of short Wikinews articles is bundled in
`examples/wikinews_sample.json` so you can try the tool immediately:

```bash
schemex run --input examples/wikinews_sample.json --output out/
```

This runs one shot, end to end, with no prompts (the default
`--mode automated`), and writes `out/report.md` + `out/state.json`.

To review and edit the clusters and schemas as they're produced instead:

```bash
schemex run --input examples/wikinews_sample.json --output out/ --mode interactive
```

In interactive mode you can, between stages:

- merge two clusters, rename a cluster, or drop a stray example from its cluster
- hand-edit a component's attributes in the abstracted schema
- accept or reject each refinement iteration's proposed schema revision,
  after reading the AI-generated example, the real example it was
  contrasted against, and the model's own comparison notes

## Interactive graph: live fixer, critic bot, coverage check, and debate chat

`schemex run` writes a static `graph.html` you can open with any local
file server. `schemex serve` instead serves a *live* version of that same
graph with a "Journalist Console" panel, so you can paste a draft and get
results in the browser without a separate CLI call per check:

```bash
schemex serve --state out/ --port 8000
```

Open `http://127.0.0.1:8000/` and click **Console** in the header. From
there you can:

- **Run Critique** — the critic bot (`schemex critique`) gives a full
  editorial verdict (structure/argument/prose scores, severity-tagged
  issues, strengths), and colours the matched cluster's graph nodes by the
  worst issue that mentions them.
- **Apply Fixer** — rewrites the draft to address every issue from the
  most recent critique (`schemex critique --fix`), right in the draft box.
- **Check Coverage** — the coverage checker (`schemex check`) reports
  present/weak/missing per schema component with ready-to-paste
  suggestions, and colours nodes accordingly.
- **Journalist Chat (Advocate vs. Skeptic)** — ask a question about your
  draft and get two opposing, schema-grounded answers: an Advocate who
  defends its current framing and a Skeptic who challenges it, so you can
  stress-test your angle before publishing.

Pick a cluster from the dropdown, or leave it on "Auto-detect from draft"
to let the model match your draft to the closest structural pattern, same
as omitting `--cluster` on the CLI commands.

`schemex serve` doesn't require `ANTHROPIC_API_KEY` just to view the
graph -- only the Console's buttons need it, same as `--api-key` on the
other subcommands.

## Input format

Either:

- a single JSON file: an array of objects, each with at least `id`,
  `title`, `text`, and optionally `source_url` and `metadata` (see
  `examples/wikinews_sample.json`), or
- a directory of `.txt` files -- each filename (minus extension) becomes
  the id and title, file contents become the text.

## CLI options

```
schemex run --input PATH --output DIR [options]

  --mode {automated,interactive}   default: automated
  --iterations N                   refinement rounds per cluster, default: 1
  --seed N                         RNG seed for which example each
                                    refinement round contrasts against
  --model NAME                     default: claude-sonnet-4-6
                                    (or set SCHEMEX_MODEL env var; check
                                    https://docs.claude.com for current
                                    model names, this default may be stale)
  --max-tokens N                   default: 4096
  --api-key KEY                    default: $ANTHROPIC_API_KEY
  --verbose                        print full prompts/responses for every
                                    model call

schemex serve --state DIR [options]

  --port, -p N                     default: 8000
  --model NAME                     default: claude-sonnet-4-6 (or SCHEMEX_MODEL)
  --max-tokens N                   default: 4096
  --api-key KEY                    default: $ANTHROPIC_API_KEY (only needed
                                    once you use a Console action)
```

## Project layout

```
schemex/
  models.py     dataclasses: Example, Cluster, SchemaComponent, Schema, RefinementRound
  llm.py        Anthropic API wrapper + defensive JSON extraction
  prompts.py    the three stage prompts (clustering / abstraction / refinement)
  pipeline.py   run_clustering(), run_abstraction(), run_refinement(), run_pipeline()
  io_utils.py   load_examples(), RunState (save/load/report), graph.html
                 rendering (incl. the Journalist Console panel)
  server.py     `schemex serve` -- stdlib HTTP server exposing critique /
                 fix / coverage / chat as JSON endpoints for the live graph
  cli.py        argparse CLI
examples/
  wikinews_sample.json   22 short news articles spanning very different
                           topics and structures, for testing
```

Every stage function in `pipeline.py` is plain and importable -- if you
want to drive this from a notebook instead of the CLI, `import schemex` and
call `run_clustering(client, examples)` etc. directly. `state.json` is
deliberately a flat, inspectable format rather than a pickle, so you can
diff schema versions across runs or feed it into another tool.

## Notes / known limitations

- Clustering and abstraction send full example text to the model. If your
  inputs are long and numerous, the prompt can get large; `prompts.py`
  truncates each example to a configurable character limit
  (`render_examples_block(..., max_chars=...)`) for exactly this reason --
  raise or lower it depending on your input sizes and model context window.
- Refinement only contrasts against one real example per iteration (as in
  the original paper's case studies). If you want to contrast against
  multiple examples per cluster per iteration, that's a small change to
  `run_refinement()` in `pipeline.py`.
- There's no automatic stopping criterion for refinement (the paper notes
  this as future work too) -- you set `--iterations` and, in interactive
  mode, accept/reject each round yourself.
- This tool makes real, billed API calls every time you run it. A full run
  over the bundled 22-example dataset with default settings makes on the
  order of 1 (clustering) + N_clusters (abstraction) + N_clusters x
  iterations x 2 (refinement: one generation call + one comparison call)
  requests.

## License

MIT. See `LICENSE`.
