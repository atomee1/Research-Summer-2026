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
        """Write a self-contained interactive HTML visualisation of the run.

        Opens in any browser — no server needed.  Uses vis.js (loaded from
        CDN) to render clusters as large hub nodes and schema components as
        smaller satellite nodes.  Clicking any node shows its details in a
        sidebar panel.
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
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f0f10;
    color: #c2c0b6;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  header {{
    padding: 12px 20px;
    border-bottom: 1px solid #2c2c2a;
    display: flex;
    align-items: center;
    gap: 20px;
    flex-shrink: 0;
    background: #1a1a1c;
  }}
  header h1 {{
    font-size: 15px;
    font-weight: 600;
    color: #e8e6de;
    letter-spacing: -0.01em;
  }}
  .stat {{
    font-size: 12px;
    color: #888780;
    background: #2c2c2a;
    padding: 3px 10px;
    border-radius: 20px;
  }}
  .stat span {{ color: #c2c0b6; font-weight: 500; }}
  .legend {{
    display: flex;
    align-items: center;
    gap: 14px;
    margin-left: auto;
    font-size: 12px;
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
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #888780;
    margin-bottom: 6px;
  }}
  .sidebar-name {{
    font-size: 16px;
    font-weight: 600;
    color: #e8e6de;
    margin-bottom: 14px;
    line-height: 1.35;
  }}
  .sidebar-section {{
    margin-bottom: 16px;
  }}
  .sidebar-label {{
    font-size: 11px;
    font-weight: 600;
    color: #5F5E5A;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
  }}
  .sidebar-body {{
    font-size: 13px;
    color: #888780;
    line-height: 1.6;
  }}
  .member-pill {{
    display: inline-block;
    background: #2c2c2a;
    color: #b4b2a9;
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 11px;
    margin: 2px 2px 2px 0;
    font-family: monospace;
  }}
  .attr-item {{
    padding: 5px 0;
    border-bottom: 1px solid #2c2c2a;
    font-size: 12px;
    color: #888780;
    line-height: 1.5;
  }}
  .attr-item:last-child {{ border-bottom: none; }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
  }}
  .badge-refined {{ background: #412402; color: #EF9F27; }}
  .badge-cluster {{ background: #26215C; color: #AFA9EC; }}
  .rel-box {{
    background: #242423;
    border-left: 2px solid #5DCAA5;
    padding: 8px 10px;
    border-radius: 0 4px 4px 0;
    font-size: 12px;
    color: #5DCAA5;
    line-height: 1.5;
  }}
  footer {{
    padding: 8px 20px;
    font-size: 11px;
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

        path = os.path.join(self.output_dir, "graph.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

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