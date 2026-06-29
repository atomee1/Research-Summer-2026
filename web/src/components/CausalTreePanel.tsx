import type { CausalEdge, CausalNode, CausalTree } from "@/lib/schema";

type Props = {
  tree: CausalTree;
};

function scorePercent(score: number) {
  return `${Math.round(score * 100)}%`;
}

function supportColor(label: CausalEdge["support_label"]) {
  switch (label) {
    case "high":
      return "bg-emerald-900 text-emerald-100";
    case "medium":
      return "bg-yellow-900 text-yellow-100";
    case "low":
      return "bg-orange-900 text-orange-100";
    case "speculative":
      return "bg-red-900 text-red-100";
    default:
      return "bg-slate-800 text-slate-100";
  }
}

function evidenceLabel(node: CausalNode) {
  return node.evidence_status.replaceAll("_", " ");
}

export function CausalTreePanel({ tree }: Props) {
  const nodeMap = new Map(tree.nodes.map((node) => [node.id, node]));
  const root = nodeMap.get(tree.root_event_id) ?? tree.nodes[0];

  function incomingEdges(targetId: string) {
    return tree.edges
      .filter((edge) => edge.to === targetId)
      .sort((a, b) => b.support_score - a.support_score);
  }

  function CauseBranch({
    targetId,
    depth = 0,
    seen = new Set<string>(),
  }: {
    targetId: string;
    depth?: number;
    seen?: Set<string>;
  }) {
    const edges = incomingEdges(targetId);

    if (edges.length === 0) {
      return null;
    }

    return (
      <div className="mt-3 space-y-3 border-l border-slate-700 pl-4">
        {edges.map((edge) => {
          const cause = nodeMap.get(edge.from);

          if (!cause) {
            return null;
          }

          const alreadySeen = seen.has(cause.id);
          const nextSeen = new Set(seen);
          nextSeen.add(cause.id);

          return (
            <div key={`${edge.from}-${edge.to}`} className="rounded-lg bg-slate-900 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{cause.label}</span>
                <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">
                  {cause.node_type.replaceAll("_", " ")}
                </span>
                <span className={`rounded px-2 py-1 text-xs ${supportColor(edge.support_label)}`}>
                  {edge.support_label} · {scorePercent(edge.support_score)}
                </span>
              </div>

              <p className="mt-2 text-sm text-slate-300">{cause.description}</p>

              <p className="mt-2 text-sm">
                <span className="text-slate-400">Relationship:</span>{" "}
                {edge.relationship}
              </p>

              <p className="mt-1 text-sm">
                <span className="text-slate-400">Rationale:</span>{" "}
                {edge.rationale}
              </p>

              <p className="mt-1 text-xs text-slate-400">
                Evidence status: {evidenceLabel(cause)}
              </p>

              {cause.evidence_quotes.length > 0 && (
                <div className="mt-2 rounded bg-slate-950 p-2">
                  <p className="text-xs font-medium text-slate-400">Evidence</p>
                  <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-slate-300">
                    {cause.evidence_quotes.map((quote, index) => (
                      <li key={index}>{quote}</li>
                    ))}
                  </ul>
                </div>
              )}

              {!alreadySeen && depth < 4 && (
                <CauseBranch targetId={cause.id} depth={depth + 1} seen={nextSeen} />
              )}
            </div>
          );
        })}
      </div>
    );
  }

  if (!root) {
    return null;
  }

  return (
    <section className="mt-6 rounded-xl border border-slate-800 bg-slate-950 p-5">
      <h3 className="text-xl font-semibold">Causal tree</h3>

      <p className="mt-2 text-slate-300">{tree.summary}</p>

      <div className="mt-5 rounded-lg border border-blue-900 bg-blue-950 p-4">
        <p className="text-sm font-medium text-blue-200">Central event</p>
        <h4 className="mt-1 text-lg font-semibold">{root.label}</h4>
        <p className="mt-2 text-sm text-blue-100">{root.description}</p>
      </div>

      <div className="mt-5">
        <h4 className="font-semibold">Possible causes and contributing factors</h4>
        <CauseBranch targetId={root.id} />
      </div>

      {tree.reporting_gaps.length > 0 && (
        <div className="mt-6 rounded-lg bg-slate-900 p-4">
          <h4 className="font-semibold">Reporting gaps</h4>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
            {tree.reporting_gaps.map((gap, index) => (
              <li key={index}>{gap}</li>
            ))}
          </ul>
        </div>
      )}

      {tree.uncertainty_notes.length > 0 && (
        <div className="mt-4 rounded-lg bg-slate-900 p-4">
          <h4 className="font-semibold">Uncertainty notes</h4>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
            {tree.uncertainty_notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
