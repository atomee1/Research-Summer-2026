"""Input loading and output saving helpers."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .models import Cluster, CoverageReport, Example, RefinementRound, Schema


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


_STATUS_MARK = {"present": "✓", "weak": "⚠", "missing": "✗"}


def write_coverage_report(report: CoverageReport, output_dir: str) -> str:
    """Write a coverage check result as both JSON and a readable Markdown
    file, named after the draft so multiple checks don't overwrite each
    other. Returns the path to the Markdown file."""
    os.makedirs(output_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(report.draft_path))[0]
    json_path = os.path.join(output_dir, f"coverage_{base}.json")
    md_path = os.path.join(output_dir, f"coverage_{base}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)

    counts = report.counts()
    lines = [
        f"# Coverage check: {os.path.basename(report.draft_path)}",
        "",
        f"**Matched schema:** {report.cluster_name} (v{report.schema_version})",
        "",
        f"**Coverage:** {counts['present']} present, {counts['weak']} weak, "
        f"{counts['missing']} missing (of {len(report.items)} components)",
        "",
    ]
    if report.overall_summary:
        lines += ["## Summary", "", report.overall_summary, ""]

    lines += ["## Component-by-component", ""]
    for item in report.items:
        mark = _STATUS_MARK.get(item.status, "?")
        lines.append(f"### {mark} {item.component_name} — {item.status}")
        lines.append("")
        lines.append(item.explanation)
        if item.suggestion:
            lines.append("")
            lines.append(f"**Suggestion:** {item.suggestion}")
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path


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

    def write_graph_html(self) -> str:
        """Write the static graph.html (no live fixer/critique/chat -- run
        `schemex serve --state <dir>` for the interactive version)."""
        html = self.render_graph_html(interactive=False)
        path = os.path.join(self.output_dir, "graph.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

    def render_graph_html(self, interactive: bool = False) -> str:
        """Build the self-contained HTML visualisation of the run, as a string.

        Uses vis.js (loaded from CDN) to render clusters as large hub nodes
        and schema components as smaller satellite nodes. Clicking any node
        shows its details in a sidebar panel.

        When interactive=True (used by `schemex serve`), also injects a
        "Journalist Console" panel: a live fixer, critic bot, coverage
        check, and an advocate/skeptic debate chat, all backed by the JSON
        API endpoints the server exposes -- so results appear right in the
        browser instead of requiring a separate CLI run per check.
        """
        # Build the node/edge data the browser will consume
        nodes: list[dict] = []
        edges: list[dict] = []
        node_details: dict[str, dict] = {}  # id -> detail dict for sidebar

        CLUSTER_COLOR = "#7F77DD"   # purple-400
        COMPONENT_COLOR = "#1D9E75" # teal-400
        REFINED_COLOR = "#EF9F27"   # amber-400

        for cluster in self.clusters:
            cid = cluster.id
            schema = self.schemas.get(cid)

            # Count refinement rounds for this cluster
            refined_count = sum(
                1 for r in self.refinement_history
                if isinstance(r, dict) and r.get("cluster_id") == cid
            )

            nodes.append({
                "id": cid,
                "label": cluster.name,
                "group": "cluster",
                "size": 28,
                "color": CLUSTER_COLOR,
                "font": {"size": 13, "color": "#ffffff", "bold": True},
                "shape": "dot",
            })
            node_details[cid] = {
                "type": "cluster",
                "name": cluster.name,
                "members": cluster.member_ids,
                "rationale": cluster.rationale,
                "refined_rounds": refined_count,
                "schema_version": schema.version if schema else 1,
            }

            if schema:
                prev_comp_id = None
                for i, comp in enumerate(schema.components):
                    comp_id = f"{cid}__comp_{i}"
                    is_refined = schema.version > 1

                    nodes.append({
                        "id": comp_id,
                        "label": comp.name,
                        "group": "component",
                        "size": 16,
                        "color": REFINED_COLOR if is_refined else COMPONENT_COLOR,
                        "font": {"size": 11, "color": "#ffffff"},
                        "shape": "dot",
                    })
                    node_details[comp_id] = {
                        "type": "component",
                        "name": comp.name,
                        "attributes": comp.attributes,
                        "relationship_to_next": comp.relationship_to_next or "",
                        "refined": is_refined,
                    }

                    # Spoke from cluster hub to first component
                    if i == 0:
                        edges.append({
                            "from": cid,
                            "to": comp_id,
                            "color": {"color": "#9F9CF0", "opacity": 0.7},
                            "width": 2,
                            "dashes": False,
                        })
                    # Chain: component -> next component
                    if prev_comp_id:
                        edges.append({
                            "from": prev_comp_id,
                            "to": comp_id,
                            "color": {"color": "#5DCAA5", "opacity": 0.8},
                            "width": 1.5,
                            "arrows": "to",
                            "label": comp.relationship_to_next[:40] + "…"
                                     if comp.relationship_to_next and len(comp.relationship_to_next) > 40
                                     else (comp.relationship_to_next or ""),
                            "font": {"size": 9, "color": "#888780", "align": "middle"},
                        })
                    prev_comp_id = comp_id

        nodes_json = json.dumps(nodes, indent=2)
        edges_json = json.dumps(edges, indent=2)
        details_json = json.dumps(node_details, indent=2)

        cluster_count = len(self.clusters)
        component_count = sum(
            len(s.components) for s in self.schemas.values()
        )
        refined_count_total = len(self.refinement_history)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Schemex — graph visualisation</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
<link  href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 15px;
    background: #0f0f10;
    color: #c2c0b6;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  header {{
    padding: 14px 22px;
    border-bottom: 1px solid #2c2c2a;
    display: flex;
    align-items: center;
    gap: 20px;
    flex-shrink: 0;
    background: #1a1a1c;
  }}
  header h1 {{
    font-family: "Playfair Display", Georgia, serif;
    font-size: 22px;
    font-weight: 700;
    color: #e8e6de;
    letter-spacing: -0.01em;
  }}
  .stat {{
    font-size: 13px;
    color: #888780;
    background: #2c2c2a;
    padding: 4px 12px;
    border-radius: 20px;
  }}
  .stat span {{ color: #c2c0b6; font-weight: 600; }}
  .legend {{
    display: flex;
    align-items: center;
    gap: 14px;
    margin-left: auto;
    font-size: 13px;
    color: #888780;
  }}
  .dot {{
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 4px;
    vertical-align: middle;
  }}
  .main {{
    display: flex;
    flex: 1;
    overflow: hidden;
  }}
  #graph {{
    flex: 1;
    background: #0f0f10;
  }}
  #sidebar {{
    width: 320px;
    border-left: 1px solid #2c2c2a;
    background: #1a1a1c;
    padding: 20px;
    overflow-y: auto;
    flex-shrink: 0;
    transition: width 0.2s;
  }}
  #sidebar.empty {{
    display: flex;
    align-items: center;
    justify-content: center;
    color: #444441;
    font-size: 13px;
    text-align: center;
  }}
  .sidebar-type {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #888780;
    margin-bottom: 6px;
  }}
  .sidebar-name {{
    font-family: "Playfair Display", Georgia, serif;
    font-size: 21px;
    font-weight: 700;
    color: #e8e6de;
    margin-bottom: 14px;
    line-height: 1.3;
  }}
  .sidebar-section {{
    margin-bottom: 16px;
  }}
  .sidebar-label {{
    font-size: 12px;
    font-weight: 600;
    color: #5F5E5A;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
  }}
  .sidebar-body {{
    font-size: 14.5px;
    color: #888780;
    line-height: 1.6;
  }}
  .member-pill {{
    display: inline-block;
    background: #2c2c2a;
    color: #b4b2a9;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 12px;
    margin: 2px 2px 2px 0;
    font-family: monospace;
  }}
  .attr-item {{
    padding: 6px 0;
    border-bottom: 1px solid #2c2c2a;
    font-size: 13.5px;
    color: #888780;
    line-height: 1.55;
  }}
  .attr-item:last-child {{ border-bottom: none; }}
  .badge {{
    display: inline-block;
    padding: 3px 9px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
  }}
  .badge-refined {{ background: #412402; color: #EF9F27; }}
  .badge-cluster {{ background: #26215C; color: #AFA9EC; }}
  .rel-box {{
    background: #242423;
    border-left: 2px solid #5DCAA5;
    padding: 9px 11px;
    border-radius: 0 4px 4px 0;
    font-size: 13.5px;
    color: #5DCAA5;
    line-height: 1.55;
  }}
  footer {{
    padding: 9px 20px;
    font-size: 12px;
    color: #444441;
    border-top: 1px solid #2c2c2a;
    background: #1a1a1c;
    flex-shrink: 0;
  }}
</style>
</head>
<body>
<header>
  <h1>Schemex — schema graph</h1>
  <div class="stat"><span>{cluster_count}</span> clusters</div>
  <div class="stat"><span>{component_count}</span> components</div>
  <div class="stat"><span>{refined_count_total}</span> refinement rounds</div>
  <div class="legend">
    <span><span class="dot" style="background:#7F77DD"></span>Cluster</span>
    <span><span class="dot" style="background:#1D9E75"></span>Component</span>
    <span><span class="dot" style="background:#EF9F27"></span>Refined</span>
  </div>
</header>
<div class="main">
  <div id="graph"></div>
  <div id="sidebar" class="empty">
    <div>Click any node<br>to see details</div>
  </div>
</div>
<footer>Drag to pan · Scroll to zoom · Click a node to inspect · Double-click to focus</footer>

<script>
const NODES = {nodes_json};
const EDGES = {edges_json};
const DETAILS = {details_json};

const container = document.getElementById("graph");
const sidebar   = document.getElementById("sidebar");

const data = {{
  nodes: new vis.DataSet(NODES),
  edges: new vis.DataSet(EDGES),
}};

const options = {{
  physics: {{
    solver: "forceAtlas2Based",
    forceAtlas2Based: {{
      gravitationalConstant: -60,
      centralGravity: 0.004,
      springLength: 120,
      springConstant: 0.05,
      damping: 0.5,
    }},
    stabilization: {{ iterations: 180 }},
  }},
  edges: {{
    smooth: {{ type: "curvedCW", roundness: 0.15 }},
    color: {{ inherit: false }},
  }},
  nodes: {{
    borderWidth: 0,
    shadow: false,
  }},
  interaction: {{
    hover: true,
    tooltipDelay: 100,
    zoomView: true,
  }},
}};

const network = new vis.Network(container, data, options);

function renderSidebar(nodeId) {{
  const d = DETAILS[nodeId];
  if (!d) return;
  sidebar.classList.remove("empty");

  if (d.type === "cluster") {{
    const pills = d.members.map(m => `<span class="member-pill">${{m}}</span>`).join("");
    sidebar.innerHTML = `
      <div class="sidebar-type">Cluster</div>
      <div class="sidebar-name">${{d.name}}</div>
      <div class="sidebar-section">
        <div class="sidebar-label">Schema version</div>
        <div class="sidebar-body">v${{d.schema_version}}
          ${{d.refined_rounds > 0
            ? `<span class="badge badge-refined" style="margin-left:6px">${{d.refined_rounds}} refinement${{d.refined_rounds > 1 ? "s" : ""}}</span>`
            : ""}}
        </div>
      </div>
      <div class="sidebar-section">
        <div class="sidebar-label">Rationale</div>
        <div class="sidebar-body">${{d.rationale}}</div>
      </div>
      <div class="sidebar-section">
        <div class="sidebar-label">Members (${{d.members.length}})</div>
        <div class="sidebar-body">${{pills}}</div>
      </div>`;
  }} else {{
    const attrs = d.attributes.map(a => `<div class="attr-item">${{a}}</div>`).join("");
    sidebar.innerHTML = `
      <div class="sidebar-type">Schema component</div>
      <div class="sidebar-name">${{d.name}}</div>
      ${{d.refined ? `<div style="margin-bottom:12px"><span class="badge badge-refined">Refined</span></div>` : ""}}
      <div class="sidebar-section">
        <div class="sidebar-label">Attributes</div>
        ${{attrs || '<div class="sidebar-body">None recorded.</div>'}}
      </div>
      ${{d.relationship_to_next ? `
      <div class="sidebar-section">
        <div class="sidebar-label">Leads into next</div>
        <div class="rel-box">${{d.relationship_to_next}}</div>
      </div>` : ""}}`;
  }}
}}

network.on("click", params => {{
  if (params.nodes.length > 0) {{
    renderSidebar(params.nodes[0]);
  }}
}});

network.on("doubleClick", params => {{
  if (params.nodes.length > 0) {{
    network.focus(params.nodes[0], {{ scale: 1.4, animation: true }});
  }}
}});
</script>
</body>
</html>"""

        if interactive:
            html = html.replace("</body>", _console_panel_html(self.clusters, self.schemas) + "\n</body>")

        return html

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


# ---------------------------------------------------------------------------
# Journalist Console -- injected into graph.html by render_graph_html() when
# interactive=True. Adds a live fixer, critic bot, coverage check, and an
# advocate/skeptic debate chat, all calling the JSON API `schemex serve`
# exposes (see server.py). Kept out of the static `schemex run` output so
# that graph.html stays a plain, dependency-free file unless you're serving.
# ---------------------------------------------------------------------------

_CONSOLE_MARKER = "/* SCHEMEX_CONSOLE_PANEL */"


def _console_panel_html(clusters: List[Cluster], schemas: Dict[str, "Schema"]) -> str:
    clusters_json = json.dumps(
        [{"id": c.id, "name": c.name} for c in clusters], indent=2
    )
    components_by_cluster = {
        cid: [comp.name for comp in schema.components]
        for cid, schema in schemas.items()
    }
    components_by_cluster_json = json.dumps(components_by_cluster, indent=2)

    return f"""
<style>
  .console-toggle-btn {{
    margin-left: 12px;
    background: #7F77DD;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-size: 13.5px;
    font-weight: 600;
    cursor: pointer;
  }}
  .console-toggle-btn:hover {{ background: #8f88e8; }}
  .console-panel {{
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100%;
    height: 62vh;
    background: #1a1a1c;
    border-top: 1px solid #2c2c2a;
    transform: translateY(100%);
    transition: transform 0.2s ease;
    z-index: 50;
    display: flex;
    flex-direction: column;
    box-shadow: 0 -8px 24px rgba(0,0,0,0.4);
  }}
  .console-panel.open {{ transform: translateY(0); }}
  .console-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    border-bottom: 1px solid #2c2c2a;
    flex-shrink: 0;
  }}
  .console-header span {{
    font-family: "Playfair Display", Georgia, serif;
    font-size: 19px;
    font-weight: 700;
    color: #e8e6de;
  }}
  .console-header button {{
    background: none; border: none; color: #888780; font-size: 20px; cursor: pointer;
  }}
  .console-body {{ flex: 1; overflow: hidden; display: flex; min-height: 0; }}
  .console-col {{ overflow-y: auto; padding: 16px 22px; min-width: 0; }}
  .console-col + .console-col {{ border-left: 1px solid #2c2c2a; }}
  .console-col-draft {{ flex: 0 0 400px; display: flex; flex-direction: column; }}
  .console-col-results {{ flex: 1 1 auto; }}
  .console-col-chat {{ flex: 0 0 400px; display: flex; flex-direction: column; }}
  .console-row {{ margin-bottom: 14px; }}
  .console-row label {{
    display: block; font-size: 12px; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; color: #5F5E5A; margin-bottom: 7px;
  }}
  .console-row select, .console-row textarea, .console-row input[type=number], .chat-input-row input {{
    width: 100%; background: #242423; border: 1px solid #2c2c2a; border-radius: 6px;
    color: #e8e6de; font-size: 15px; padding: 9px 11px; font-family: inherit;
  }}
  .console-row textarea {{ min-height: 220px; resize: vertical; line-height: 1.6; }}
  .word-count-row {{
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12.5px; color: #888780; margin: -6px 0 14px;
  }}
  .console-actions {{ display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
  .console-actions button, .chat-input-row button, .cuts-apply-btn {{
    background: #2c2c2a; color: #c2c0b6; border: 1px solid #3a3a37; border-radius: 6px;
    padding: 8px 14px; font-size: 13.5px; font-weight: 500; cursor: pointer;
  }}
  .console-actions button:hover:not(:disabled), .chat-input-row button:hover, .cuts-apply-btn:hover {{ background: #3a3a37; }}
  .console-actions button:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  .console-status {{ font-size: 13px; color: #888780; margin-bottom: 10px; min-height: 18px; }}
  .verdict {{ font-size: 16px; color: #e8e6de; margin-bottom: 12px; line-height: 1.5; font-weight: 500; }}
  .scores {{ display: flex; gap: 16px; font-size: 13.5px; color: #888780; margin-bottom: 14px; }}
  .scores b {{ color: #e8e6de; }}
  .issue-group {{ margin-bottom: 16px; }}
  .issue-group-title {{
    font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    color: #5F5E5A; margin-bottom: 8px;
  }}
  .issue-row {{
    border-left: 3px solid #888780; background: #242423; border-radius: 0 6px 6px 0;
    padding: 10px 12px; margin-bottom: 7px; font-size: 13.5px; line-height: 1.55;
  }}
  .issue-head {{ color: #e8e6de; font-weight: 600; margin-bottom: 4px; }}
  .issue-sev {{ font-weight: 700; text-transform: uppercase; font-size: 11px; margin-right: 5px; }}
  .issue-quote {{ font-style: italic; color: #b4b2a9; margin: 4px 0; }}
  .issue-detail {{ color: #888780; }}
  .cut-row label {{ display: flex; gap: 8px; align-items: flex-start; cursor: pointer; }}
  .cut-row input[type=checkbox] {{ margin-top: 3px; flex-shrink: 0; transform: scale(1.15); }}
  .cuts-apply-btn {{ margin-top: 4px; }}
  .console-divider {{ border-top: 1px solid #2c2c2a; margin: 16px 0; }}
  .chat-log {{ flex: 1; overflow-y: auto; margin-bottom: 10px; }}
  .chat-question {{ font-size: 14.5px; color: #e8e6de; font-weight: 700; margin: 10px 0 7px; }}
  .chat-answer {{
    border-left: 3px solid #888780; background: #242423; border-radius: 0 6px 6px 0;
    padding: 9px 12px; margin-bottom: 7px; font-size: 13.5px; line-height: 1.55; color: #b4b2a9;
  }}
  .chat-answer b {{ color: #e8e6de; display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }}
  .chat-input-row {{ display: flex; gap: 8px; flex-shrink: 0; }}
  .chat-input-row input {{ flex: 1; }}
</style>

<div class="console-panel" id="consolePanel">
  <div class="console-header">
    <span>Journalist Console</span>
    <button id="consoleClose" aria-label="Close">&times;</button>
  </div>
  <div class="console-body">
    <div class="console-col console-col-draft">
      <div class="console-row">
        <label>Cluster</label>
        <select id="clusterSelect"><option value="">Auto-detect from draft</option></select>
      </div>
      <div class="console-row">
        <label>Draft</label>
        <textarea id="draftText" placeholder="Paste your draft here..."></textarea>
      </div>
      <div class="word-count-row">
        <span id="wordCountLabel">0 words</span>
      </div>
      <div class="console-row">
        <label>Target word limit (for Suggest Cuts)</label>
        <input type="number" id="targetWords" min="1" placeholder="e.g. 600">
      </div>
      <div class="console-actions">
        <button id="btnCritique">Run Critique</button>
        <button id="btnCoverage">Check Coverage</button>
        <button id="btnFix" disabled>Apply Fixer</button>
        <button id="btnCuts">Suggest Cuts</button>
      </div>
      <div id="consoleStatus" class="console-status"></div>
    </div>
    <div class="console-col console-col-results">
      <div id="consoleResults"></div>
    </div>
    <div class="console-col console-col-chat">
      <div class="console-row">
        <label>Journalist Chat — Advocate vs. Skeptic</label>
      </div>
      <div id="chatLog" class="chat-log"></div>
      <div class="chat-input-row">
        <input id="chatInput" type="text" placeholder="Ask a question about your draft...">
        <button id="btnChatSend">Ask</button>
      </div>
    </div>
  </div>
</div>

<script>
{_CONSOLE_MARKER}
(function () {{
  const CLUSTERS = {clusters_json};
  const COMPONENTS_BY_CLUSTER = {components_by_cluster_json};
  const SEV_COLOR = {{ critical: "#E0584A", major: "#EF9F27", minor: "#7F77DD" }};
  const COV_COLOR = {{ present: "#1D9E75", weak: "#EF9F27", missing: "#E0584A" }};

  let lastCritique = null;
  let lastClusterId = null;
  let chatHistory = [];

  function init() {{
    const header = document.querySelector("header");
    const btn = document.createElement("button");
    btn.id = "consoleToggle";
    btn.textContent = "Console";
    btn.className = "console-toggle-btn";
    header.appendChild(btn);

    const panel = document.getElementById("consolePanel");
    btn.addEventListener("click", () => panel.classList.toggle("open"));
    document.getElementById("consoleClose").addEventListener("click", () => panel.classList.remove("open"));

    const select = document.getElementById("clusterSelect");
    CLUSTERS.forEach(c => {{
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
    }});

    document.getElementById("btnCritique").addEventListener("click", runCritique);
    document.getElementById("btnCoverage").addEventListener("click", runCoverage);
    document.getElementById("btnFix").addEventListener("click", runFix);
    document.getElementById("btnCuts").addEventListener("click", runCuts);
    document.getElementById("btnChatSend").addEventListener("click", sendChat);
    document.getElementById("chatInput").addEventListener("keydown", e => {{
      if (e.key === "Enter") sendChat();
    }});
    document.getElementById("draftText").addEventListener("input", updateWordCount);
    document.getElementById("targetWords").addEventListener("input", updateWordCount);
    updateWordCount();
  }}

  function setStatus(msg, isError) {{
    const el = document.getElementById("consoleStatus");
    el.textContent = msg || "";
    el.style.color = isError ? "#E0584A" : "#888780";
  }}

  function escapeHtml(s) {{
    return (s == null ? "" : String(s))
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }}

  function currentDraft() {{ return document.getElementById("draftText").value.trim(); }}
  function currentClusterId() {{ return document.getElementById("clusterSelect").value || null; }}

  function wordCount(text) {{
    return (text.match(/\\S+/g) || []).length;
  }}

  function updateWordCount() {{
    const words = wordCount(currentDraft());
    const target = parseInt(document.getElementById("targetWords").value, 10);
    const label = document.getElementById("wordCountLabel");
    if (target && !isNaN(target) && target > 0) {{
      const diff = words - target;
      label.textContent = diff > 0
        ? `${{words}} words (${{diff}} over ${{target}}-word limit)`
        : `${{words}} words (${{Math.abs(diff)}} under ${{target}}-word limit)`;
      label.style.color = diff > 0 ? "#E0584A" : "#1D9E75";
    }} else {{
      label.textContent = `${{words}} words`;
      label.style.color = "#888780";
    }}
  }}

  async function postJSON(url, body) {{
    const res = await fetch(url, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(body),
    }});
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || ("HTTP " + res.status));
    return payload;
  }}

  function paintComponentColors(colorByLabel) {{
    // `data`/`network` are declared with const in the graph script above; if
    // vis.js failed to load (e.g. CDN blocked), that declaration throws and
    // leaves them in the temporal dead zone -- referencing them anywhere,
    // even in a typeof check, then throws ReferenceError. Swallow that here
    // so a blocked CDN degrades to "no live repaint" instead of surfacing a
    // confusing JS error in the console status line.
    try {{
      if (typeof network === "undefined" || typeof data === "undefined") return;
    }} catch (e) {{
      return;
    }}
    const updates = [];
    data.nodes.forEach(node => {{
      if (node.group !== "component") return;
      const color = colorByLabel[node.label];
      if (!color) return;
      updates.push(Object.assign({{}}, data.nodes.get(node.id), {{
        color: {{
          background: color, border: color,
          highlight: {{ background: color, border: "#ffffff" }},
          hover: {{ background: color, border: "#ffffff" }},
        }},
      }}));
    }});
    if (updates.length) {{
      data.nodes.remove(updates.map(u => u.id));
      data.nodes.add(updates);
      network.redraw();
    }}
  }}

  function issueListHtml(title, issues) {{
    if (!issues || !issues.length) return "";
    const rows = issues.map(i => `
      <div class="issue-row" style="border-left-color:${{SEV_COLOR[i.severity] || '#888780'}}">
        <div class="issue-head"><span class="issue-sev" style="color:${{SEV_COLOR[i.severity] || '#888780'}}">${{escapeHtml(i.severity)}}</span>${{escapeHtml(i.issue)}}</div>
        ${{(i.quote || i.claim) ? `<div class="issue-quote">"${{escapeHtml(i.quote || i.claim)}}"</div>` : ""}}
        <div class="issue-detail">${{escapeHtml(i.detail)}}</div>
      </div>`).join("");
    return `<div class="issue-group"><div class="issue-group-title">${{escapeHtml(title)}}</div>${{rows}}</div>`;
  }}

  async function runCritique() {{
    const draft = currentDraft();
    if (!draft) {{ setStatus("Paste a draft first.", true); return; }}
    setStatus("Running critique...");
    try {{
      const result = await postJSON("/api/critique", {{ draft_text: draft, cluster_id: currentClusterId() }});
      lastCritique = result.critique;
      lastClusterId = result.cluster_id;
      document.getElementById("btnFix").disabled = false;
      setStatus(`Matched cluster: ${{result.cluster_name}}`);

      const c = lastCritique;
      document.getElementById("consoleResults").innerHTML = `
        <div class="verdict">${{escapeHtml(c.verdict)}}</div>
        <div class="scores">
          <span>Structure <b>${{c.score.structure}}</b>/10</span>
          <span>Argument <b>${{c.score.argument}}</b>/10</span>
          <span>Prose <b>${{c.score.prose}}</b>/10</span>
        </div>
        ${{issueListHtml("Structural issues", c.structural_issues)}}
        ${{issueListHtml("Argumentative issues", c.argumentative_issues)}}
        ${{issueListHtml("Prose issues", c.prose_issues)}}
        ${{(c.strengths && c.strengths.length) ? `<div class="issue-group"><div class="issue-group-title">Strengths</div>${{c.strengths.map(s => `<div class="issue-row" style="border-left-color:#1D9E75">${{escapeHtml(s)}}</div>`).join("")}}</div>` : ""}}
      `;

      // Colour graph nodes by the worst issue severity that mentions them --
      // same heuristic `schemex critique` uses when injecting into a static graph.html.
      // Scoped to the matched cluster's components, embedded at render time
      // (COMPONENTS_BY_CLUSTER) rather than read off the live vis.js dataset,
      // so this still works even if the vis.js CDN failed to load.
      const allIssues = [].concat(c.structural_issues, c.argumentative_issues, c.prose_issues);
      const compNames = COMPONENTS_BY_CLUSTER[result.cluster_id] || [];
      const rank = {{ critical: 3, major: 2, minor: 1 }};
      const worst = {{}};
      allIssues.forEach(issue => {{
        const text = (issue.issue + " " + issue.detail + " " + (issue.quote || "") + " " + (issue.claim || "")).toLowerCase();
        compNames.forEach(name => {{
          if (text.includes(name.toLowerCase()) && (!worst[name] || rank[issue.severity] > rank[worst[name]])) {{
            worst[name] = issue.severity;
          }}
        }});
      }});
      const colorMap = {{}};
      compNames.forEach(name => {{ colorMap[name] = worst[name] ? SEV_COLOR[worst[name]] : "#1D9E75"; }});
      paintComponentColors(colorMap);
    }} catch (e) {{
      setStatus("Critique failed: " + e.message, true);
    }}
  }}

  async function runCoverage() {{
    const draft = currentDraft();
    if (!draft) {{ setStatus("Paste a draft first.", true); return; }}
    setStatus("Checking coverage...");
    try {{
      const result = await postJSON("/api/coverage", {{ draft_text: draft, cluster_id: currentClusterId() }});
      lastClusterId = result.cluster_id;
      setStatus(`Matched cluster: ${{result.cluster_name}}`);

      const r = result.coverage;
      document.getElementById("consoleResults").innerHTML = `
        ${{r.overall_summary ? `<div class="verdict">${{escapeHtml(r.overall_summary)}}</div>` : ""}}
        ${{r.items.map(item => `
          <div class="issue-row" style="border-left-color:${{COV_COLOR[item.status] || '#888780'}}">
            <div class="issue-head"><span class="issue-sev" style="color:${{COV_COLOR[item.status] || '#888780'}}">${{escapeHtml(item.status)}}</span>${{escapeHtml(item.component_name)}}</div>
            <div class="issue-detail">${{escapeHtml(item.explanation)}}</div>
            ${{item.suggestion ? `<div class="issue-quote">${{escapeHtml(item.suggestion)}}</div>` : ""}}
          </div>`).join("")}}
      `;
      const colorMap = {{}};
      r.items.forEach(item => {{ colorMap[item.component_name] = COV_COLOR[item.status] || "#888780"; }});
      paintComponentColors(colorMap);
    }} catch (e) {{
      setStatus("Coverage check failed: " + e.message, true);
    }}
  }}

  async function runFix() {{
    if (!lastCritique) {{ setStatus("Run a critique first.", true); return; }}
    setStatus("Rewriting draft...");
    try {{
      const result = await postJSON("/api/fix", {{ draft_text: currentDraft(), critique: lastCritique }});
      document.getElementById("draftText").value = result.fixed_draft;
      document.getElementById("btnFix").disabled = true;
      lastCritique = null;
      updateWordCount();
      setStatus("Draft rewritten. Re-run critique to verify.");
    }} catch (e) {{
      setStatus("Fixer failed: " + e.message, true);
    }}
  }}

  async function runCuts() {{
    const draft = currentDraft();
    const target = parseInt(document.getElementById("targetWords").value, 10);
    if (!draft) {{ setStatus("Paste a draft first.", true); return; }}
    if (!target || target <= 0) {{ setStatus("Enter a target word limit first.", true); return; }}
    setStatus("Finding cuts...");
    try {{
      const result = await postJSON("/api/cuts", {{ draft_text: draft, target_words: target, cluster_id: currentClusterId() }});
      lastClusterId = result.cluster_id;
      setStatus(`Matched cluster: ${{result.cluster_name}}`);

      const c = result.cuts;
      if (c.over_by === 0) {{
        document.getElementById("consoleResults").innerHTML =
          `<div class="verdict">${{escapeHtml(c.notes || "Already at or under the target word count.")}}</div>`;
        return;
      }}

      let running = 0;
      const rows = c.suggestions.map((s, i) => {{
        running += s.word_count;
        const reachedTarget = running >= c.over_by;
        const warn = s.found_in_draft ? "" : `<div class="issue-quote" style="color:#E0584A">Could not find this exact text in the draft -- may need manual removal.</div>`;
        return `
          <div class="issue-row cut-row" style="border-left-color:${{reachedTarget ? '#1D9E75' : '#EF9F27'}}">
            <label>
              <input type="checkbox" class="cut-checkbox" data-quote="${{encodeURIComponent(s.quote)}}" ${{s.found_in_draft ? "" : "disabled"}}>
              <span>
                <div class="issue-quote">"${{escapeHtml(s.quote)}}"</div>
                <div class="issue-detail">${{escapeHtml(s.reason)}} <b>(${{s.word_count}} words)</b></div>
                ${{warn}}
              </span>
            </label>
          </div>`;
      }}).join("");

      document.getElementById("consoleResults").innerHTML = `
        <div class="verdict">${{c.current_words}} words, ${{c.over_by}} over your ${{c.target_words}}-word target.${{c.notes ? " " + escapeHtml(c.notes) : ""}}</div>
        <div class="issue-group">
          <div class="issue-group-title">Suggested cuts (safest first -- check the ones to apply)</div>
          ${{rows}}
        </div>
        <button id="btnApplyCuts" class="cuts-apply-btn">Apply checked cuts</button>
      `;
      document.getElementById("btnApplyCuts").addEventListener("click", applyCuts);
    }} catch (e) {{
      setStatus("Suggest cuts failed: " + e.message, true);
    }}
  }}

  function applyCuts() {{
    let draft = currentDraft();
    const checked = document.querySelectorAll(".cut-checkbox:checked");
    let removed = 0;
    checked.forEach(cb => {{
      const quote = decodeURIComponent(cb.dataset.quote);
      if (quote && draft.includes(quote)) {{
        draft = draft.replace(quote, "");
        removed++;
      }}
    }});
    // Tidy up double spaces / blank lines left behind by removed sentences.
    draft = draft.replace(/[ \\t]{{2,}}/g, " ").replace(/\\n{{3,}}/g, "\\n\\n").replace(/ +\\n/g, "\\n").trim();
    document.getElementById("draftText").value = draft;
    updateWordCount();
    setStatus(removed ? `Applied ${{removed}} cut${{removed === 1 ? "" : "s"}}.` : "No cuts applied -- nothing was checked.");
  }}

  function renderChat() {{
    const log = document.getElementById("chatLog");
    log.innerHTML = chatHistory.map(turn => `
      <div class="chat-question">${{escapeHtml(turn.question)}}</div>
      <div class="chat-answer" style="border-left-color:#1D9E75"><b>Advocate</b>${{escapeHtml(turn.advocate)}}</div>
      <div class="chat-answer" style="border-left-color:#E0584A"><b>Skeptic</b>${{escapeHtml(turn.skeptic)}}</div>
    `).join("");
    log.scrollTop = log.scrollHeight;
  }}

  async function sendChat() {{
    const input = document.getElementById("chatInput");
    const question = input.value.trim();
    const draft = currentDraft();
    if (!question) return;
    if (!draft) {{ setStatus("Paste a draft first.", true); return; }}
    input.value = "";
    setStatus("Asking the debate bot...");
    try {{
      const result = await postJSON("/api/chat", {{
        draft_text: draft,
        cluster_id: currentClusterId() || lastClusterId,
        question: question,
        history: chatHistory,
      }});
      lastClusterId = result.cluster_id;
      chatHistory.push({{ question: question, advocate: result.advocate, skeptic: result.skeptic }});
      renderChat();
      setStatus("");
    }} catch (e) {{
      setStatus("Chat failed: " + e.message, true);
    }}
  }}

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", init);
  }} else {{
    init();
  }}
}})();
</script>"""


# ---------------------------------------------------------------------------
# Visual coverage report (HTML)
# ---------------------------------------------------------------------------

_STATUS_COLOR = {
    "present": "#1D9E75",
    "weak":    "#EF9F27",
    "missing": "#E0584A",
}
_STATUS_BG = {
    "present": "#0F2A22",
    "weak":    "#2E2008",
    "missing": "#2E1411",
}
_STATUS_LABEL = {"present": "Present", "weak": "Weak", "missing": "Missing"}


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_coverage_html(report: "CoverageReport", output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(report.draft_path))[0]
    html_path = os.path.join(output_dir, f"coverage_{base}.html")

    counts = report.counts()
    total = max(len(report.items), 1)
    present_pct = round(100 * counts["present"] / total)
    weak_pct    = round(100 * counts["weak"]    / total)
    p_end = present_pct
    w_end = p_end + weak_pct
    ring_css = (
        f"conic-gradient({_STATUS_COLOR['present']} 0% {p_end}%, "
        f"{_STATUS_COLOR['weak']} {p_end}% {w_end}%, "
        f"{_STATUS_COLOR['missing']} {w_end}% 100%)"
    )

    cards_html = []
    for item in report.items:
        color = _STATUS_COLOR.get(item.status, "#888780")
        bg    = _STATUS_BG.get(item.status, "#1a1a1c")
        label = _STATUS_LABEL.get(item.status, item.status)
        suggestion_html = (
            f'<div class="suggestion"><span class="suggestion-label">Draft suggestion</span>{_esc(item.suggestion)}</div>'
            if item.suggestion else ""
        )
        cards_html.append(f"""
        <div class="card" style="border-left-color:{color};background:{bg}1A">
          <div class="card-head">
            <span class="badge" style="background:{bg};color:{color}">{label}</span>
            <span class="card-title">{_esc(item.component_name)}</span>
          </div>
          <div class="card-body">{_esc(item.explanation)}</div>
          {suggestion_html}
        </div>""")

    summary_html = (
        f'<div class="summary"><div class="summary-label">Editor\u2019s note</div>{_esc(report.overall_summary)}</div>'
        if report.overall_summary else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Coverage — {_esc(os.path.basename(report.draft_path))}</title>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f0f10;color:#c2c0b6;min-height:100vh;padding:32px 24px 60px}}
  .wrap{{max-width:720px;margin:0 auto}}
  .eyebrow{{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#888780;margin-bottom:6px}}
  h1{{font-size:22px;font-weight:600;color:#e8e6de;margin-bottom:4px}}
  .subtitle{{font-size:13px;color:#888780;margin-bottom:28px}}
  .top{{display:flex;align-items:center;gap:28px;background:#1a1a1c;border:1px solid #2c2c2a;border-radius:12px;padding:24px;margin-bottom:24px}}
  .ring{{width:96px;height:96px;border-radius:50%;background:{ring_css};flex-shrink:0;display:flex;align-items:center;justify-content:center;position:relative}}
  .ring::after{{content:"";position:absolute;width:68px;height:68px;border-radius:50%;background:#1a1a1c}}
  .ring-pct{{position:relative;z-index:1;font-size:18px;font-weight:700;color:#e8e6de}}
  .legend{{display:flex;flex-direction:column;gap:8px}}
  .legend-row{{display:flex;align-items:center;gap:8px;font-size:13px}}
  .legend-dot{{width:9px;height:9px;border-radius:50%;flex-shrink:0}}
  .legend-count{{color:#e8e6de;font-weight:600;margin-left:2px}}
  .summary{{background:#1a1a1c;border:1px solid #2c2c2a;border-radius:10px;padding:16px 18px;margin-bottom:24px;font-size:13px;line-height:1.6}}
  .summary-label{{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#888780;margin-bottom:6px;display:block}}
  .section-label{{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#5F5E5A;margin-bottom:12px}}
  .card{{border-left:3px solid;border-radius:0 10px 10px 0;padding:14px 16px;margin-bottom:10px}}
  .card-head{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
  .badge{{font-size:10px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:3px 9px;border-radius:20px;flex-shrink:0}}
  .card-title{{font-size:14px;font-weight:600;color:#e8e6de}}
  .card-body{{font-size:13px;line-height:1.6;color:#b4b2a9}}
  .suggestion{{margin-top:10px;padding-top:10px;border-top:1px dashed #2c2c2a;font-size:12.5px;line-height:1.6;color:#c2c0b6;font-style:italic}}
  .suggestion-label{{display:block;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#5F5E5A;margin-bottom:4px;font-style:normal}}
</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">Schemex coverage check</div>
  <h1>{_esc(os.path.basename(report.draft_path))}</h1>
  <div class="subtitle">Matched schema: {_esc(report.cluster_name)} (v{report.schema_version})</div>
  <div class="top">
    <div class="ring"><span class="ring-pct">{present_pct}%</span></div>
    <div class="legend">
      <div class="legend-row"><span class="legend-dot" style="background:{_STATUS_COLOR['present']}"></span>Present<span class="legend-count">{counts['present']}</span></div>
      <div class="legend-row"><span class="legend-dot" style="background:{_STATUS_COLOR['weak']}"></span>Weak<span class="legend-count">{counts['weak']}</span></div>
      <div class="legend-row"><span class="legend-dot" style="background:{_STATUS_COLOR['missing']}"></span>Missing<span class="legend-count">{counts['missing']}</span></div>
    </div>
  </div>
  {summary_html}
  <div class="section-label">Component-by-component</div>
  {''.join(cards_html)}
</div>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path


# ---------------------------------------------------------------------------
# Coverage overlay injection into graph.html
# ---------------------------------------------------------------------------

_COVERAGE_COLORS = {
    "present": "#1D9E75",
    "weak":    "#EF9F27",
    "missing": "#E0584A",
}
_COVERAGE_MARKER = "/* SCHEMEX_COVERAGE_OVERLAY */"


def inject_coverage_into_graph(report: "CoverageReport", graph_html_path: str) -> bool:
    if not os.path.exists(graph_html_path):
        return False

    with open(graph_html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Remove any previous overlay
    if _COVERAGE_MARKER in html:
        start = html.index(_COVERAGE_MARKER)
        script_open  = html.rfind("<script>", 0, start)
        script_close = html.find("</script>", start)
        if script_open != -1 and script_close != -1:
            html = html[:script_open] + html[script_close + len("</script>"):]

    overlay_items = {
        item.component_name: {
            "status":      item.status,
            "color":       _COVERAGE_COLORS.get(item.status, "#888780"),
            "explanation": item.explanation,
            "suggestion":  item.suggestion,
            "draft":       os.path.basename(report.draft_path),
            "cluster":     report.cluster_name,
        }
        for item in report.items
    }

    overlay_json  = json.dumps(overlay_items, indent=2)
    draft_name    = os.path.basename(report.draft_path)
    cluster_name  = report.cluster_name
    counts        = report.counts()

    overlay_script = f"""
<script>
{_COVERAGE_MARKER}
// Coverage overlay — injected by `schemex check`
// Draft: {draft_name}  |  Schema: {cluster_name}
(function () {{
  const COVERAGE = {overlay_json};

  function buildUpdates() {{
    const updates = [];
    data.nodes.forEach(function (node) {{
      if (node.group !== "component") return;
      const label = node.label || "";
      let hit = COVERAGE[label];
      if (!hit) {{
        const lowerLabel = label.toLowerCase();
        for (const [name, info] of Object.entries(COVERAGE)) {{
          if (name.toLowerCase() === lowerLabel) {{ hit = info; break; }}
        }}
      }}
      if (hit) {{
        updates.push({{
          id: node.id,
          color: {{
            background: hit.color,
            border:     hit.color,
            highlight:  {{ background: hit.color, border: "#ffffff" }},
            hover:      {{ background: hit.color, border: "#ffffff" }},
          }},
        }});
        if (typeof DETAILS !== "undefined" && DETAILS[node.id]) {{
          DETAILS[node.id].coverage = hit;
        }}
      }}
    }});
    return updates;
  }}

  function paintNodes() {{
    const updates = buildUpdates();
    if (updates.length === 0) return;
    // Remove then re-add so vis.js treats them as new and repaints
    const ids = updates.map(function(u) {{ return u.id; }});
    const originals = ids.map(function(id) {{ return data.nodes.get(id); }});
    data.nodes.remove(ids);
    data.nodes.add(updates.map(function(u, i) {{
      return Object.assign({{}}, originals[i], u);
    }}));
    network.redraw();
  }}

  function applyOverlay() {{
    if (typeof data === "undefined" || typeof network === "undefined") {{
      setTimeout(applyOverlay, 80);
      return;
    }}

    // Paint immediately and again after stabilization to catch both cases
    paintNodes();
    network.once("stabilized", function() {{ paintNodes(); }});

    // 2. Patch sidebar to show coverage panel
    const _origRender = window._origRenderSidebar || window.renderSidebar;
    window._origRenderSidebar = _origRender;
    window.renderSidebar = function (nodeId) {{
      _origRender(nodeId);
      const d = DETAILS[nodeId];
      if (!d || d.type !== "component" || !d.coverage) return;
      const cov = d.coverage;
      const colorMap = {{ present: "#1D9E75", weak: "#EF9F27", missing: "#E0584A" }};
      const bgMap    = {{ present: "#0F2A22", weak: "#2E2008", missing: "#2E1411" }};
      const labelMap = {{ present: "Present",  weak: "Weak",    missing: "Missing"  }};
      const color = colorMap[cov.status] || "#888780";
      const bg    = bgMap[cov.status]    || "#1a1a1c";
      const label = labelMap[cov.status] || cov.status;
      const suggHtml = cov.suggestion
        ? `<div style="margin-top:10px;padding-top:10px;border-top:1px dashed #2c2c2a">
             <div style="font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#5F5E5A;margin-bottom:4px">Draft suggestion</div>
             <div style="font-size:12px;line-height:1.6;color:#c2c0b6;font-style:italic">${{cov.suggestion}}</div>
           </div>`
        : "";
      const panel = document.createElement("div");
      panel.style.cssText = `margin-top:14px;border-left:3px solid ${{color}};background:${{bg}}26;border-radius:0 8px 8px 0;padding:12px 14px`;
      panel.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span style="font-size:10px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:3px 9px;border-radius:20px;background:${{bg}};color:${{color}}">${{label}}</span>
          <span style="font-size:11px;color:#888780">in <em>${{cov.draft}}</em></span>
        </div>
        <div style="font-size:13px;line-height:1.6;color:#b4b2a9">${{cov.explanation}}</div>
        ${{suggHtml}}`;
      const sidebar = document.getElementById("sidebar");
      if (sidebar) sidebar.appendChild(panel);
    }};

    // 3. Update header legend
    const legend = document.querySelector(".legend");
    if (legend) {{
      legend.innerHTML = `
        <span style="font-size:11px;color:#5F5E5A;margin-right:4px">Coverage:</span>
        <span><span class="dot" style="background:#1D9E75"></span>Present ({counts["present"]})</span>
        <span><span class="dot" style="background:#EF9F27"></span>Weak ({counts["weak"]})</span>
        <span><span class="dot" style="background:#E0584A"></span>Missing ({counts["missing"]})</span>
        <span style="margin-left:8px;padding-left:8px;border-left:1px solid #2c2c2a;color:#5F5E5A;font-size:11px">Draft: {draft_name}</span>`;
    }}
  }}

  applyOverlay();
}})();
</script>"""

    html = html.replace("</body>", overlay_script + "\n</body>") if "</body>" in html else html + overlay_script

    with open(graph_html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return True


# ---------------------------------------------------------------------------
# Critique report output
# ---------------------------------------------------------------------------

_SEV_MARK = {"critical": "🔴", "major": "🟡", "minor": "🔵"}
_SEV_COLOR = {"critical": "#E0584A", "major": "#EF9F27", "minor": "#7F77DD"}


def write_critique_report(report: "CritiqueReport", output_dir: str) -> tuple:
    """Write critic (and optionally fixer) output as JSON, Markdown, and HTML.
    Returns (md_path, html_path)."""
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(report.draft_path))[0]
    json_path = os.path.join(output_dir, f"critique_{base}.json")
    md_path   = os.path.join(output_dir, f"critique_{base}.md")
    html_path = os.path.join(output_dir, f"critique_{base}.html")

    # JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)

    # Markdown
    def fmt_issues_md(issues, label):
        if not issues:
            return f"### {label}\nNone identified.\n"
        lines = [f"### {label}\n"]
        for item in issues:
            mark = _SEV_MARK.get(item.severity, "•")
            q = f"\n  > \"{item.quote or item.claim}\"" if (item.quote or item.claim) else ""
            lines.append(f"{mark} **{item.issue}** `[{item.severity}]`{q}\n  {item.detail}\n")
        return "\n".join(lines)

    score = report.score
    md_lines = [
        f"# Critique: {os.path.basename(report.draft_path)}\n",
        f"**Verdict:** {report.verdict}\n",
        f"**Schema:** {report.cluster_name}\n",
        f"| Structure | Argument | Prose |",
        f"|-----------|----------|-------|",
        f"| {score.get('structure', '?')}/10 | {score.get('argument', '?')}/10 | {score.get('prose', '?')}/10 |\n",
    ]
    if report.strengths:
        md_lines += ["## Strengths\n"] + [f"- {s}" for s in report.strengths] + [""]
    md_lines.append(fmt_issues_md(report.structural_issues, "Structural issues"))
    md_lines.append(fmt_issues_md(report.argumentative_issues, "Argumentative issues"))
    md_lines.append(fmt_issues_md(report.prose_issues, "Prose issues"))
    if report.fixed_draft:
        md_lines += ["\n---\n## Fixed draft\n", report.fixed_draft]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # HTML
    def score_bar(val, color):
        pct = max(0, min(100, int(val or 0) * 10))
        return (f'<div style="display:flex;align-items:center;gap:8px">'
                f'<div style="flex:1;height:6px;background:#2c2c2a;border-radius:3px">'
                f'<div style="width:{pct}%;height:100%;background:{color};border-radius:3px"></div></div>'
                f'<span style="font-size:12px;color:#e8e6de;width:28px">{val}/10</span></div>')

    def issue_cards(issues, category):
        if not issues:
            return '<div style="font-size:13px;color:#5F5E5A;padding:8px 0">None identified.</div>'
        cards = []
        for item in issues:
            color = _SEV_COLOR.get(item.severity, "#888780")
            q = item.quote or item.claim
            quote_html = (f'<div style="margin:8px 0;padding:8px 12px;background:#0f0f10;'
                          f'border-left:2px solid {color};font-size:12px;color:#888780;'
                          f'font-style:italic">{_esc(q)}</div>') if q else ""
            cards.append(
                f'<div style="border-left:3px solid {color};background:{color}18;'
                f'border-radius:0 8px 8px 0;padding:12px 14px;margin-bottom:8px">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                f'<span style="font-size:10px;font-weight:700;letter-spacing:.04em;'
                f'text-transform:uppercase;padding:2px 8px;border-radius:20px;'
                f'background:{color}33;color:{color}">{item.severity}</span>'
                f'<span style="font-size:13px;font-weight:600;color:#e8e6de">{_esc(item.issue)}</span>'
                f'</div>{quote_html}'
                f'<div style="font-size:13px;line-height:1.6;color:#b4b2a9">{_esc(item.detail)}</div>'
                f'</div>'
            )
        return "".join(cards)

    strengths_html = ""
    if report.strengths:
        items = "".join(f'<li style="padding:4px 0;font-size:13px;color:#b4b2a9">{_esc(s)}</li>'
                        for s in report.strengths)
        strengths_html = (f'<div style="background:#1a1a1c;border:1px solid #2c2c2a;'
                          f'border-radius:10px;padding:16px 18px;margin-bottom:20px">'
                          f'<div style="font-size:10px;font-weight:700;letter-spacing:.08em;'
                          f'text-transform:uppercase;color:#1D9E75;margin-bottom:10px">Strengths</div>'
                          f'<ul style="list-style:none;padding:0">{items}</ul></div>')

    fixed_html = ""
    if report.fixed_draft:
        paras = "".join(
            f'<p style="margin-bottom:12px;font-size:14px;line-height:1.7;color:#c2c0b6">{_esc(p)}</p>'
            for p in report.fixed_draft.split("\n\n") if p.strip()
        )
        fixed_html = (f'<hr style="border:none;border-top:1px solid #2c2c2a;margin:28px 0">'
                      f'<div style="font-size:11px;font-weight:700;letter-spacing:.08em;'
                      f'text-transform:uppercase;color:#7F77DD;margin-bottom:16px">Fixed draft</div>'
                      f'{paras}')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Critique — {_esc(os.path.basename(report.draft_path))}</title>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        background:#0f0f10;color:#c2c0b6;min-height:100vh;padding:32px 24px 60px}}
  .wrap{{max-width:760px;margin:0 auto}}
  h1{{font-size:22px;font-weight:600;color:#e8e6de;margin-bottom:4px}}
  h2{{font-size:14px;font-weight:600;color:#e8e6de;margin:24px 0 12px;
      letter-spacing:.02em;text-transform:uppercase;font-size:11px;color:#5F5E5A}}
  .verdict{{font-size:15px;line-height:1.5;color:#EF9F27;font-style:italic;
            margin:12px 0 20px;padding:12px 16px;background:#2E200826;
            border-left:3px solid #EF9F27;border-radius:0 8px 8px 0}}
  .scores{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:24px}}
  .score-card{{background:#1a1a1c;border:1px solid #2c2c2a;border-radius:10px;padding:14px 16px}}
  .score-label{{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
                color:#888780;margin-bottom:8px}}
</style>
</head>
<body>
<div class="wrap">
  <div style="font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;
              color:#888780;margin-bottom:6px">Schemex critic</div>
  <h1>{_esc(os.path.basename(report.draft_path))}</h1>
  <div style="font-size:13px;color:#888780;margin-bottom:16px">Schema: {_esc(report.cluster_name)}</div>
  <div class="verdict">{_esc(report.verdict)}</div>
  <div class="scores">
    <div class="score-card">
      <div class="score-label">Structure</div>
      {score_bar(score.get('structure', 0), '#7F77DD')}
    </div>
    <div class="score-card">
      <div class="score-label">Argument</div>
      {score_bar(score.get('argument', 0), '#EF9F27')}
    </div>
    <div class="score-card">
      <div class="score-label">Prose</div>
      {score_bar(score.get('prose', 0), '#1D9E75')}
    </div>
  </div>
  {strengths_html}
  <h2>Structural issues</h2>
  {issue_cards(report.structural_issues, 'structural')}
  <h2>Argumentative issues</h2>
  {issue_cards(report.argumentative_issues, 'argumentative')}
  <h2>Prose issues</h2>
  {issue_cards(report.prose_issues, 'prose')}
  {fixed_html}
</div>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return md_path, html_path


# ---------------------------------------------------------------------------
# Critique overlay injection into graph.html
# ---------------------------------------------------------------------------

_CRITIQUE_MARKER = "/* SCHEMEX_CRITIQUE_OVERLAY */"

_CRITIQUE_SEV_COLOR = {
    "critical": "#E0584A",
    "major":    "#EF9F27",
    "minor":    "#7F77DD",
    "clean":    "#1D9E75",
}
_CRITIQUE_SEV_RANK = {"critical": 3, "major": 2, "minor": 1, "clean": 0}


def inject_critique_into_graph(report: "CritiqueReport", graph_html_path: str) -> bool:
    """Inject critique bot results into graph.html.

    Each component node is coloured by the worst issue that mentions it:
      red   = critical issue
      amber = major issue
      blue  = minor issue
      green = no issues flagged (clean)

    Clicking a node shows the verdict, scores, and any issues that reference
    that component in the sidebar.
    """
    if not os.path.exists(graph_html_path):
        return False

    with open(graph_html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Remove any previous critique overlay
    if _CRITIQUE_MARKER in html:
        start        = html.index(_CRITIQUE_MARKER)
        script_open  = html.rfind("<script>", 0, start)
        script_close = html.find("</script>", start)
        if script_open != -1 and script_close != -1:
            html = html[:script_open] + html[script_close + len("</script>"):]

    # Build per-component issue map
    # key = component name (lower), value = {severity, issues[]}
    comp_issues: dict = {}

    all_issues = (
        [("structural",     i) for i in report.structural_issues] +
        [("argumentative",  i) for i in report.argumentative_issues] +
        [("prose",          i) for i in report.prose_issues]
    )

    for category, issue in all_issues:
        # Issues reference components by name in their detail text or issue label
        # We do a broad scan: if the component name appears in the issue text, link it
        text_to_scan = (issue.issue + " " + issue.detail + " " +
                        issue.quote + " " + issue.claim).lower()
        for comp_name in set(comp_issues.keys()):
            if comp_name in text_to_scan:
                existing = comp_issues[comp_name]
                if (_CRITIQUE_SEV_RANK.get(issue.severity, 0) >
                        _CRITIQUE_SEV_RANK.get(existing["worst_severity"], 0)):
                    existing["worst_severity"] = issue.severity
                existing["issues"].append({
                    "category": category,
                    "issue":    issue.issue,
                    "detail":   issue.detail,
                    "severity": issue.severity,
                    "quote":    issue.quote or issue.claim,
                })

    # Also seed every component name from structural issues explicitly
    for issue in report.structural_issues:
        key = issue.issue.lower()
        if key not in comp_issues:
            comp_issues[key] = {"worst_severity": issue.severity, "issues": []}
        comp_issues[key]["issues"].append({
            "category": "structural",
            "issue":    issue.issue,
            "detail":   issue.detail,
            "severity": issue.severity,
            "quote":    issue.quote or issue.claim,
        })
        if (_CRITIQUE_SEV_RANK.get(issue.severity, 0) >
                _CRITIQUE_SEV_RANK.get(comp_issues[key]["worst_severity"], 0)):
            comp_issues[key]["worst_severity"] = issue.severity

    comp_issues_json = json.dumps(comp_issues, indent=2)
    score            = report.score
    verdict          = report.verdict
    draft_name       = os.path.basename(report.draft_path)
    cluster_name     = report.cluster_name
    total            = report.total_issues()
    critical         = report.critical_count()

    sev_colors_json = json.dumps(_CRITIQUE_SEV_COLOR)

    overlay_script = f"""
<script>
{_CRITIQUE_MARKER}
// Critique overlay — injected by `schemex critique`
// Draft: {draft_name}  |  Schema: {cluster_name}
(function () {{
  const COMP_ISSUES        = {comp_issues_json};
  const STRUCTURAL_ISSUES  = {json.dumps([i.to_dict() for i in report.structural_issues])};
  const ARGUMENTATIVE_ISSUES = {json.dumps([i.to_dict() for i in report.argumentative_issues])};
  const PROSE_ISSUES       = {json.dumps([i.to_dict() for i in report.prose_issues])};
  const SEV_COLOR          = {sev_colors_json};
  const VERDICT            = {json.dumps(verdict)};
  const SCORE              = {json.dumps(score)};
  const DRAFT_NAME         = {json.dumps(draft_name)};
  const CLUSTER_NAME       = {json.dumps(cluster_name)};
  const TOTAL_ISSUES       = {total};
  const CRITICAL           = {critical};

  const SEV_RANK = {{ critical: 3, major: 2, minor: 1, clean: 0 }};

  // Build a flat list of all issues for broad matching
  const ALL_ISSUES = [
    ...STRUCTURAL_ISSUES.map(i => Object.assign({{category:"structural"}}, i)),
    ...ARGUMENTATIVE_ISSUES.map(i => Object.assign({{category:"argumentative"}}, i)),
    ...PROSE_ISSUES.map(i => Object.assign({{category:"prose"}}, i)),
  ];

  function matchIssues(label) {{
    const lower = label.toLowerCase().replace(/[^a-z0-9 ]/g, "");
    const words = lower.split(" ").filter(w => w.length > 3);
    let worst = "clean";
    const matched = [];
    for (const iss of ALL_ISSUES) {{
      const issText = (iss.issue + " " + iss.detail + " " + (iss.quote||"") + " " + (iss.claim||"")).toLowerCase();
      // Match if any meaningful word from the component label appears in the issue text
      const hits = words.filter(w => issText.includes(w));
      if (hits.length >= 1) {{
        if ((SEV_RANK[iss.severity] || 0) > (SEV_RANK[worst] || 0)) {{
          worst = iss.severity;
        }}
        matched.push(iss);
      }}
    }}
    // Fallback: if no specific match, assign a colour based on overall scores
    // so the graph is never all-yellow even when issues don't name components
    if (matched.length === 0 && ALL_ISSUES.length > 0) {{
      const avgScore = (
        (SCORE.structure || 5) + (SCORE.argument || 5) + (SCORE.prose || 5)
      ) / 3;
      if (avgScore <= 4)      worst = "major";
      else if (avgScore <= 6) worst = "minor";
      else                    worst = "clean";
    }}
    return {{ worst, issues: matched }};
  }}

  function buildUpdates() {{
    const updates = [];
    data.nodes.forEach(function (node) {{
      if (node.group !== "component") return;
      const label  = node.label || "";
      const result = matchIssues(label);
      const color  = SEV_COLOR[result.worst] || SEV_COLOR.clean;
      updates.push({{
        id: node.id,
        color: {{
          background: color,
          border:     color,
          highlight:  {{ background: color, border: "#ffffff" }},
          hover:      {{ background: color, border: "#ffffff" }},
        }},
      }});
      if (typeof DETAILS !== "undefined" && DETAILS[node.id]) {{
        DETAILS[node.id].critique = {{ worst: result.worst, issues: result.issues, color }};
      }}
    }});
    return updates;
  }}

  function paintNodes() {{
    const updates = buildUpdates();
    if (updates.length === 0) return;
    const ids       = updates.map(u => u.id);
    const originals = ids.map(id => data.nodes.get(id));
    data.nodes.remove(ids);
    data.nodes.add(updates.map((u, i) => Object.assign({{}}, originals[i], u)));
    network.redraw();
  }}

  function applyOverlay() {{
    if (typeof data === "undefined" || typeof network === "undefined") {{
      setTimeout(applyOverlay, 80);
      return;
    }}

    paintNodes();
    network.once("stabilized", function () {{ paintNodes(); }});

    // Patch sidebar to show critique panel on click
    const _orig = window._origRenderSidebar || window.renderSidebar;
    window._origRenderSidebar = _orig;
    window.renderSidebar = function (nodeId) {{
      _orig(nodeId);
      const d = DETAILS[nodeId];
      if (!d || d.type !== "component" || !d.critique) return;
      const crit  = d.critique;
      const color = crit.color;
      const sevLabel = {{ critical:"Critical", major:"Major", minor:"Minor", clean:"Clean" }};

      const issueCards = (crit.issues || []).map(function(iss) {{
        const c = SEV_COLOR[iss.severity] || "#888780";
        const q = iss.quote
          ? `<div style="margin:6px 0;padding:6px 10px;background:#0f0f10;border-left:2px solid ${{c}};font-size:11px;color:#888780;font-style:italic">${{iss.quote}}</div>`
          : "";
        return `<div style="margin-bottom:8px;padding:8px 10px;background:${{c}}18;border-radius:6px;border-left:2px solid ${{c}}">
          <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px">
            <span style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:${{c}}">${{iss.severity}}</span>
            <span style="font-size:12px;font-weight:600;color:#e8e6de">${{iss.issue}}</span>
          </div>
          ${{q}}
          <div style="font-size:12px;line-height:1.5;color:#b4b2a9">${{iss.detail}}</div>
        </div>`;
      }}).join("");

      const panel = document.createElement("div");
      panel.style.cssText = `margin-top:14px;border-left:3px solid ${{color}};background:${{color}}18;border-radius:0 8px 8px 0;padding:12px 14px`;
      panel.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
          <span style="font-size:10px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:2px 8px;border-radius:20px;background:${{color}}33;color:${{color}}">${{sevLabel[crit.worst] || crit.worst}}</span>
          <span style="font-size:11px;color:#888780">critic</span>
        </div>
        ${{issueCards || '<div style="font-size:12px;color:#1D9E75">No issues flagged for this component.</div>'}}`;
      const sidebar = document.getElementById("sidebar");
      if (sidebar) sidebar.appendChild(panel);
    }};

    // Update header legend to show critique summary
    const legend = document.querySelector(".legend");
    if (legend) {{
      const scoreStr = `S:${{SCORE.structure||"?"}} A:${{SCORE.argument||"?"}} P:${{SCORE.prose||"?"}}`;
      legend.innerHTML = `
        <span style="font-size:11px;color:#5F5E5A;margin-right:2px">Critic:</span>
        <span><span class="dot" style="background:#E0584A"></span>Critical</span>
        <span><span class="dot" style="background:#EF9F27"></span>Major</span>
        <span><span class="dot" style="background:#7F77DD"></span>Minor</span>
        <span><span class="dot" style="background:#1D9E75"></span>Clean</span>
        <span style="margin-left:8px;padding-left:8px;border-left:1px solid #2c2c2a;color:#EF9F27;font-size:11px;font-style:italic;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${{VERDICT}}">${{VERDICT}}</span>
        <span style="margin-left:8px;color:#5F5E5A;font-size:11px">${{scoreStr}}</span>`;
    }}
  }}

  applyOverlay();
}})();
</script>"""

    html = (html.replace("</body>", overlay_script + "\n</body>")
            if "</body>" in html else html + overlay_script)

    with open(graph_html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return True