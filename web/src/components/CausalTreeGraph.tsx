"use client";

import { useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";

import type { CausalEdge, CausalNode, CausalTree } from "@/lib/schema";

type CausalNodeData = {
  label: string;
  description: string;
  nodeType: string;
  evidenceStatus: string;
  quoteCount: number;
};

type Props = {
  tree: CausalTree;
};

function supportColor(label: CausalEdge["support_label"]) {
  switch (label) {
    case "high":
      return "#10b981";
    case "medium":
      return "#eab308";
    case "low":
      return "#f97316";
    case "speculative":
      return "#ef4444";
    default:
      return "#94a3b8";
  }
}

function supportWidth(score: number) {
  if (score >= 0.75) return 4;
  if (score >= 0.5) return 3;
  if (score >= 0.25) return 2;
  return 1.5;
}

function formatLabel(value: string) {
  return value.replaceAll("_", " ");
}

function supportLabelText(label: CausalEdge["support_label"]) {
  switch (label) {
    case "high":
      return "High support";
    case "medium":
      return "Medium support";
    case "low":
      return "Low support";
    case "speculative":
      return "Speculative";
    default:
      return "Support unclear";
  }
}

function CausalNodeCard({ data }: NodeProps) {
  const nodeData = data as unknown as CausalNodeData;

  return (
    <div className="w-64 rounded-xl border border-slate-700 bg-slate-950 p-3 shadow-xl">
      <Handle type="target" position={Position.Left} className="!bg-slate-300" />

      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-100">{nodeData.label}</h4>
      </div>

      <p className="mt-2 line-clamp-3 text-xs text-slate-300">
        {nodeData.description}
      </p>

      <div className="mt-3 flex flex-wrap gap-1">
        <span className="rounded bg-blue-950 px-2 py-1 text-[10px] text-blue-100">
          {formatLabel(nodeData.nodeType)}
        </span>

        <span className="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-200">
          {formatLabel(nodeData.evidenceStatus)}
        </span>

        {nodeData.quoteCount > 0 && (
          <span className="rounded bg-emerald-950 px-2 py-1 text-[10px] text-emerald-100">
            {nodeData.quoteCount} evidence item{nodeData.quoteCount === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <Handle type="source" position={Position.Right} className="!bg-slate-300" />
    </div>
  );
}

const nodeTypes = {
  causalNode: CausalNodeCard,
} satisfies NodeTypes;

function buildDepthMap(tree: CausalTree) {
  const incomingByTarget = new Map<string, CausalEdge[]>();

  for (const edge of tree.edges) {
    const current = incomingByTarget.get(edge.to) ?? [];
    current.push(edge);
    incomingByTarget.set(edge.to, current);
  }

  const depthMap = new Map<string, number>();
  const queue: Array<{ id: string; depth: number }> = [
    { id: tree.root_event_id, depth: 0 },
  ];

  while (queue.length > 0) {
    const item = queue.shift();

    if (!item) continue;

    const previousDepth = depthMap.get(item.id);

    if (previousDepth !== undefined && previousDepth >= item.depth) {
      continue;
    }

    depthMap.set(item.id, item.depth);

    const incoming = incomingByTarget.get(item.id) ?? [];

    for (const edge of incoming) {
      queue.push({ id: edge.from, depth: item.depth + 1 });
    }
  }

  for (const node of tree.nodes) {
    if (!depthMap.has(node.id)) {
      depthMap.set(node.id, 0);
    }
  }

  return depthMap;
}

function treeToFlow(tree: CausalTree) {
  const depthMap = buildDepthMap(tree);
  const maxDepth = Math.max(...Array.from(depthMap.values()), 0);

  const nodesByDepth = new Map<number, CausalNode[]>();

  for (const node of tree.nodes) {
    const depth = depthMap.get(node.id) ?? 0;
    const current = nodesByDepth.get(depth) ?? [];
    current.push(node);
    nodesByDepth.set(depth, current);
  }

  const flowNodes: Node[] = [];

  for (const [depth, depthNodes] of nodesByDepth.entries()) {
    depthNodes.forEach((node, index) => {
      flowNodes.push({
        id: node.id,
        type: "causalNode",
        position: {
          x: (maxDepth - depth) * 430,
          y: index * 250,
        },
        data: {
          label: node.label,
          description: node.description,
          nodeType: node.node_type,
          evidenceStatus: node.evidence_status,
          quoteCount: node.evidence_quotes.length,
        } satisfies CausalNodeData,
      });
    });
  }

  const flowEdges: Edge[] = tree.edges.map((edge) => ({
    id: `${edge.from}-${edge.to}`,
    source: edge.from,
    target: edge.to,
    label: supportLabelText(edge.support_label),
    animated: edge.support_label === "speculative",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: supportColor(edge.support_label),
    },
    style: {
      stroke: supportColor(edge.support_label),
      strokeWidth: supportWidth(edge.support_score),
    },
    labelStyle: {
      fill: "#e2e8f0",
      fontSize: 11,
      fontWeight: 600,
    },
    labelBgStyle: {
      fill: "#020617",
      fillOpacity: 0.9,
    },
  }));

  return { nodes: flowNodes, edges: flowEdges };
}

function CausalGraphLegend() {
  return (
    <div className="mb-4 rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm text-slate-300">
      <h4 className="font-semibold text-slate-100">How to read this graph</h4>

      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>
          Arrows point from a proposed cause or contributing factor toward the
          event it helps explain.
        </li>
        <li>
          Edge labels show how strongly the article supports the causal link,
          not the real-world probability that the cause is true.
        </li>
        <li>
          Thicker green edges are strongly supported. Yellow/orange edges are
          weaker or more interpretive. Red/animated edges are speculative.
        </li>
        <li>
          Click a node or edge to inspect evidence, rationale, and reporting
          questions.
        </li>
      </ul>
    </div>
  );
}

export function CausalTreeGraph({ tree }: Props) {
  const { nodes, edges } = useMemo(() => treeToFlow(tree), [tree]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    tree.root_event_id
  );
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const selectedNode =
    tree.nodes.find((node) => node.id === selectedNodeId) ??
    tree.nodes.find((node) => node.id === tree.root_event_id) ??
    tree.nodes[0];

  const selectedIncomingEdges = selectedNode
    ? tree.edges.filter((edge) => edge.to === selectedNode.id)
    : [];

  const selectedOutgoingEdges = selectedNode
    ? tree.edges.filter((edge) => edge.from === selectedNode.id)
    : [];

  const selectedEdge = selectedEdgeId
  ? tree.edges.find((edge) => `${edge.from}-${edge.to}` === selectedEdgeId)
  : null;

  const nodeById = new Map(tree.nodes.map((node) => [node.id, node]));

  return (
    <section className="mt-6 rounded-xl border border-slate-800 bg-slate-950 p-5">
      <div className="mb-4">
        <h3 className="text-xl font-semibold">Causal tree</h3>
        <p className="mt-2 text-sm text-slate-300">{tree.summary}</p>
      </div>

      <CausalGraphLegend />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="h-[760px] overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            minZoom={0.2}
            maxZoom={1.5}
            onNodeClick={(_, node) => {
              setSelectedNodeId(node.id);
              setSelectedEdgeId(null);
            }}
            onEdgeClick={(_, edge) => {
              setSelectedEdgeId(edge.id);
            }}
          >
          </ReactFlow>
        </div>

        <aside className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          {selectedEdge && (
            <div className="mb-5 rounded-lg border border-purple-800 bg-purple-950 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-purple-200">
                Selected causal link
              </p>

              <h4 className="mt-2 text-sm font-semibold text-purple-50">
                {nodeById.get(selectedEdge.from)?.label ?? selectedEdge.from}
                {" → "}
                {nodeById.get(selectedEdge.to)?.label ?? selectedEdge.to}
              </h4>

              <p className="mt-3 text-sm text-purple-100">
                {selectedEdge.relationship}
              </p>

              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded bg-slate-950 px-2 py-1 text-xs text-slate-100">
                  {supportLabelText(selectedEdge.support_label)}
                </span>

                <span className="rounded bg-slate-950 px-2 py-1 text-xs text-slate-100">
                  Article support score: {Math.round(selectedEdge.support_score * 100)}%
                </span>

                <span className="rounded bg-slate-950 px-2 py-1 text-xs text-slate-100">
                  {selectedEdge.evidence_status.replaceAll("_", " ")}
                </span>
              </div>

              <div className="mt-4">
                <h5 className="text-sm font-semibold text-purple-100">
                  Why this score?
                </h5>
                <p className="mt-1 text-sm text-purple-100">
                  {selectedEdge.rationale}
                </p>
              </div>

              {selectedEdge.reporting_questions.length > 0 && (
                <div className="mt-4">
                  <h5 className="text-sm font-semibold text-purple-100">
                    Reporting questions
                  </h5>

                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-purple-100">
                    {selectedEdge.reporting_questions.map((question, index) => (
                      <li key={index}>{question}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {selectedNode ? (
            <>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Selected node
              </p>

              <h4 className="mt-2 text-lg font-semibold text-slate-100">
                {selectedNode.label}
              </h4>

              <p className="mt-2 text-sm text-slate-300">
                {selectedNode.description}
              </p>

              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded bg-blue-950 px-2 py-1 text-xs text-blue-100">
                  {formatLabel(selectedNode.node_type)}
                </span>

                <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-200">
                  {formatLabel(selectedNode.evidence_status)}
                </span>
              </div>

              {selectedNode.evidence_quotes.length > 0 && (
                <div className="mt-5">
                  <h5 className="text-sm font-semibold text-slate-200">
                    Evidence
                  </h5>

                  <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-slate-300">
                    {selectedNode.evidence_quotes.map((quote, index) => (
                      <li key={index}>{quote}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedIncomingEdges.length > 0 && (
                <div className="mt-5">
                  <h5 className="text-sm font-semibold text-slate-200">
                    Possible causes
                  </h5>

                  <div className="mt-2 space-y-2">
                    {selectedIncomingEdges.map((edge) => {
                      const cause = nodeById.get(edge.from);

                      return (
                        <div
                          key={`${edge.from}-${edge.to}`}
                          className="rounded bg-slate-950 p-3 text-sm"
                        >
                          <p className="font-medium text-slate-100">
                            {cause?.label ?? edge.from}
                          </p>
                          <p className="mt-1 text-slate-300">
                            {edge.relationship}
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            Support: {edge.support_label} ·{" "}
                            {Math.round(edge.support_score * 100)}%
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            {edge.rationale}
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            Evidence status: {edge.evidence_status.replaceAll("_", " ")}
                          </p>

                          {edge.reporting_questions.length > 0 && (
                            <div className="mt-2 rounded bg-slate-900 p-2">
                              <p className="text-xs font-semibold text-slate-300">
                                Reporting questions
                              </p>

                              <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-slate-400">
                                {edge.reporting_questions.map((question, index) => (
                                  <li key={index}>{question}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {selectedOutgoingEdges.length > 0 && (
                <div className="mt-5">
                  <h5 className="text-sm font-semibold text-slate-200">
                    Consequences / effects
                  </h5>

                  <div className="mt-2 space-y-2">
                    {selectedOutgoingEdges.map((edge) => {
                      const effect = nodeById.get(edge.to);

                      return (
                        <div
                          key={`${edge.from}-${edge.to}`}
                          className="rounded bg-slate-950 p-3 text-sm"
                        >
                          <p className="font-medium text-slate-100">
                            {effect?.label ?? edge.to}
                          </p>
                          <p className="mt-1 text-slate-300">
                            {edge.relationship}
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            Support: {edge.support_label} ·{" "}
                            {Math.round(edge.support_score * 100)}%
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {tree.reporting_gaps.length > 0 && (
                <div className="mt-5">
                  <h5 className="text-sm font-semibold text-slate-200">
                    Reporting gaps
                  </h5>

                  <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-slate-300">
                    {tree.reporting_gaps.map((gap, index) => (
                      <li key={index}>{gap}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-slate-300">Select a node to inspect it.</p>
          )}
        </aside>
      </div>

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
