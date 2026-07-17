import json

with open("schemex_out/state.json") as f:
    state = json.load(f)

with open("schemex_out/coverage_my_draft.json") as f:
    coverage = json.load(f)

status_colors = {
    "present": "#4CAF50",
    "weak": "#FFC107",
    "missing": "#F44336"
}

cluster_id = coverage["cluster_id"]  # "cluster_2"
schema_components = state["schemas"][cluster_id]["components"]

coverage_lookup = {
    item["component_name"]: item
    for item in coverage["items"]
}

overlay = {}  # keyed by node id, e.g. "cluster_2__comp_0"
for idx, comp in enumerate(schema_components):
    node_id = f"{cluster_id}__comp_{idx}"
    name = comp["name"]
    match = coverage_lookup.get(name)
    if match:
        overlay[node_id] = {
            "color": status_colors[match["status"]],
            "status": match["status"],
            "tooltip": match["explanation"] if match["status"] != "present" else "Covered",
            "suggestion": match["suggestion"]
        }
    else:
        overlay[node_id] = {
            "color": "#9E9E9E",
            "status": "unknown",
            "tooltip": "Not evaluated against this draft",
            "suggestion": ""
        }

with open("schemex_out/coverage_overlay.json", "w") as f:
    json.dump(overlay, f, indent=2)

print(f"Wrote overlay for {len(overlay)} nodes in {cluster_id}")