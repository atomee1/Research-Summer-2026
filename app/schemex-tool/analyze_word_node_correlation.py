"""
analyze_node_word_correlation.py
─────────────────────────────────────────────────────────────────
Tests whether schema node count (components per cluster) reliably
correlates with article word count across the 22 Wikinews examples.

Usage (run from app/schemex-tool/):
    py analyze_node_word_correlation.py

Reads:
    schemex_out/state.json          — cluster assignments + schemas
    examples/wikinews_sample.json   — raw article texts

Writes:
    schemex_out/node_word_analysis.md    — readable report
    schemex_out/node_word_analysis.json  — raw data for further use
"""

import json
import math
import os
import sys


# ── helpers ──────────────────────────────────────────────────────────────────

def word_count(text: str) -> int:
    return len(text.split())


def mean(values):
    return sum(values) / len(values) if values else 0.0


def pearson(xs, ys):
    """Pearson r between two equal-length lists. Returns (r, interpretation)."""
    n = len(xs)
    if n < 2:
        return 0.0, "insufficient data"
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy  = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0, "no variance"
    r = num / (dx * dy)
    if   abs(r) >= 0.7: interp = "strong"
    elif abs(r) >= 0.4: interp = "moderate"
    elif abs(r) >= 0.2: interp = "weak"
    else:                interp = "negligible"
    direction = "positive" if r > 0 else "negative"
    return round(r, 4), f"{interp} {direction}"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── paths ────────────────────────────────────────────────────────────────────

STATE_PATH    = os.path.join("schemex_out", "state.json")
EXAMPLES_PATH = os.path.join("examples", "wikinews_sample.json")
OUT_DIR       = "schemex_out"

for p in [STATE_PATH, EXAMPLES_PATH]:
    if not os.path.exists(p):
        print(f"Error: file not found: {p}")
        print("Run this script from app/schemex-tool/ after `schemex run`.")
        sys.exit(1)

state    = load_json(STATE_PATH)
examples = load_json(EXAMPLES_PATH)


# ── build article lookup ──────────────────────────────────────────────────────

articles = {ex["id"]: ex for ex in examples}


# ── build per-article records ─────────────────────────────────────────────────

records = []   # {article_id, title, cluster_id, cluster_name, node_count, word_count}

clusters  = state.get("clusters", [])
schemas   = state.get("schemas", {})

for cluster in clusters:
    cid          = cluster["id"]
    cluster_name = cluster["name"]
    schema       = schemas.get(cid, {})
    node_count   = len(schema.get("components", []))
    member_ids   = cluster.get("member_ids", [])

    for art_id in member_ids:
        art = articles.get(art_id)
        if art is None:
            print(f"  Warning: article '{art_id}' in cluster but not in examples — skipping.")
            continue
        wc = word_count(art.get("text", ""))
        records.append({
            "article_id":   art_id,
            "title":        art.get("title", art_id),
            "cluster_id":   cid,
            "cluster_name": cluster_name,
            "node_count":   node_count,
            "word_count":   wc,
        })

if not records:
    print("No records built — check that state.json member_ids match example ids.")
    sys.exit(1)

print(f"Built {len(records)} article records across {len(clusters)} clusters.")


# ── global correlation ────────────────────────────────────────────────────────

all_nodes = [r["node_count"] for r in records]
all_words = [r["word_count"] for r in records]

global_r, global_interp = pearson(all_nodes, all_words)

# words-per-node ratio
ratios = [r["word_count"] / r["node_count"] for r in records if r["node_count"] > 0]
mean_ratio  = round(mean(ratios))
min_ratio   = round(min(ratios))
max_ratio   = round(max(ratios))

print(f"\nGlobal Pearson r  : {global_r}  ({global_interp})")
print(f"Mean words/node   : {mean_ratio}  (range {min_ratio}–{max_ratio})")


# ── per-cluster breakdown ─────────────────────────────────────────────────────

cluster_stats = {}
for cluster in clusters:
    cid     = cluster["id"]
    members = [r for r in records if r["cluster_id"] == cid]
    if not members:
        continue
    wcs        = [m["word_count"] for m in members]
    node_count = members[0]["node_count"]   # same for all in cluster
    cluster_stats[cid] = {
        "name":         cluster["name"],
        "node_count":   node_count,
        "article_count": len(members),
        "mean_word_count": round(mean(wcs)),
        "min_word_count":  min(wcs),
        "max_word_count":  max(wcs),
        "words_per_node":  round(mean(wcs) / node_count) if node_count else 0,
        "members":         members,
    }

print("\nPer-cluster summary:")
print(f"{'Cluster':<45} {'Nodes':>5} {'Articles':>8} {'Mean WC':>8} {'WC/Node':>8}")
print("─" * 80)
for cid, s in sorted(cluster_stats.items(), key=lambda x: x[1]["node_count"]):
    name = s["name"][:44]
    print(f"{name:<45} {s['node_count']:>5} {s['article_count']:>8} "
          f"{s['mean_word_count']:>8} {s['words_per_node']:>8}")


# ── hypothesis verdict ────────────────────────────────────────────────────────

if global_r >= 0.7:
    verdict = ("SUPPORTED — strong positive correlation. Node count is a "
               "reliable proxy for article length in this corpus.")
elif global_r >= 0.4:
    verdict = ("PARTIALLY SUPPORTED — moderate positive correlation. "
               "Node count tracks length directionally but not reliably "
               "enough to use as a predictor.")
elif global_r >= 0.2:
    verdict = ("WEAKLY SUPPORTED — weak correlation. Node count and word "
               "count vary somewhat together but other factors dominate.")
else:
    verdict = ("NOT SUPPORTED — negligible correlation. Node count does "
               "not predict article length in this corpus. Structural "
               "complexity and length appear to be independent.")

print(f"\nHypothesis: ~20 nodes ≈ 1,000 words")
print(f"Verdict   : {verdict}")
if mean_ratio:
    print(f"Observed  : ~{mean_ratio} words per node (not 50 as the hypothesis assumes)")


# ── write outputs ─────────────────────────────────────────────────────────────

# JSON
json_out = {
    "global_pearson_r":    global_r,
    "global_interpretation": global_interp,
    "mean_words_per_node": mean_ratio,
    "min_words_per_node":  min_ratio,
    "max_words_per_node":  max_ratio,
    "hypothesis_verdict":  verdict,
    "cluster_stats":       {
        cid: {k: v for k, v in s.items() if k != "members"}
        for cid, s in cluster_stats.items()
    },
    "records": records,
}
json_path = os.path.join(OUT_DIR, "node_word_analysis.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(json_out, f, indent=2)

# Markdown report
md_lines = [
    "# Node count vs word count — correlation analysis\n",
    f"**Corpus:** {len(records)} articles across {len(clusters)} clusters  \n",
    f"**Global Pearson r:** `{global_r}` ({global_interp})  \n",
    f"**Mean words per node:** {mean_ratio} (range {min_ratio}–{max_ratio})  \n",
    "",
    "## Hypothesis",
    "> ~20 nodes ≈ 1,000 words (i.e. ~50 words per schema component)\n",
    f"**Verdict:** {verdict}\n",
    "",
    "## Per-cluster breakdown\n",
    "| Cluster | Nodes | Articles | Mean word count | Words / node |",
    "|---------|-------|----------|-----------------|--------------|",
]
for cid, s in sorted(cluster_stats.items(), key=lambda x: x[1]["node_count"]):
    md_lines.append(
        f"| {s['name']} | {s['node_count']} | {s['article_count']} "
        f"| {s['mean_word_count']} | {s['words_per_node']} |"
    )

md_lines += [
    "",
    "## Per-article detail\n",
    "| Article | Cluster | Nodes | Word count | Words / node |",
    "|---------|---------|-------|------------|--------------|",
]
for r in sorted(records, key=lambda x: x["word_count"], reverse=True):
    wpn = round(r["word_count"] / r["node_count"]) if r["node_count"] else "—"
    title = r["title"][:50]
    md_lines.append(
        f"| {title} | {r['cluster_name'][:30]} "
        f"| {r['node_count']} | {r['word_count']} | {wpn} |"
    )

md_lines += [
    "",
    "## Interpretation notes\n",
    "- Node count is **fixed per cluster** — all articles in the same cluster "
      "share the same schema and therefore the same node count. This means the "
      "correlation is driven entirely by whether longer articles cluster together "
      "with more-complex schemas.",
    "- A negligible or weak r here does **not** mean schemas are useless — it "
      "means structural complexity and length are partially independent variables.",
    "- To strengthen the test, re-run Schemex on a larger and more varied corpus "
      "(100+ articles) where node counts vary more across clusters.",
]

md_path = os.path.join(OUT_DIR, "node_word_analysis.md")
with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(md_lines))

print(f"\nOutputs written:")
print(f"  {md_path}")
print(f"  {json_path}")