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