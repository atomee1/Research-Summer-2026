import { z } from "zod";

export const SchemaCardSchema = z.object({
  headline: z.string(),
  topic: z.string(),
  story_type: z.string(),
  trigger_event: z.string(),
  central_conflict: z.string(),
  main_actors: z.array(z.string()),
  affected_group: z.string(),
  stakes: z.string(),
  causal_chain: z.array(z.string()),
  narrative_schema: z.string(),
  analogy_signature: z.string(),
  missing_information_a_reporter_might_seek: z.array(z.string()),
});

export type SchemaCard = z.infer<typeof SchemaCardSchema>;

export type ArticleRecord = {
  id: string;
  title: string;
  date?: string;
  category?: string;
  url?: string;
  schema: SchemaCard;
};

export const EvidenceStatusSchema = z.enum([
  "explicitly_reported",
  "strongly_implied",
  "weakly_implied",
  "disputed_or_attributed",
  "background_context",
  "unsupported_hypothesis",
]);

export const CausalNodeTypeSchema = z.enum([
  "root_event",
  "event",
  "possible_cause",
  "contributing_factor",
  "context",
  "consequence",
]);

export const CausalNodeSchema = z.object({
  id: z.string().describe("A short stable id like event_1 or cause_2."),
  label: z.string().describe("Short human-readable label for the event or cause."),
  description: z.string().describe("One or two sentence explanation."),
  node_type: CausalNodeTypeSchema,
  evidence_status: EvidenceStatusSchema,
  evidence_quotes: z.array(z.string()).describe(
    "Short quotes or paraphrased article fragments that support this node. Use an empty array if no evidence appears in the article."
  ),
});

export const CausalEdgeSchema = z.object({
  from: z.string().describe("The id of the cause node."),
  to: z.string().describe("The id of the effect/event node."),
  relationship: z.string().describe("Plain-English causal relationship."),
  support_score: z.number().min(0).max(1).describe(
    "How strongly the article supports this causal link, from 0 to 1. This is not real-world probability."
  ),
  support_label: z.enum(["high", "medium", "low", "speculative"]),
  rationale: z.string().describe("Why this link received this support score."),
});

export const CausalTreeSchema = z.object({
  title: z.string(),
  root_event_id: z.string().describe("The id of the central event being explained."),
  summary: z.string().describe("Short summary of the causal tree."),
  nodes: z.array(CausalNodeSchema),
  edges: z.array(CausalEdgeSchema),
  reporting_gaps: z.array(z.string()).describe(
    "Questions a journalist would need to answer to verify or improve the causal account."
  ),
  uncertainty_notes: z.array(z.string()).describe(
    "Important caveats about what the article does not establish."
  ),
});

export type EvidenceStatus = z.infer<typeof EvidenceStatusSchema>;
export type CausalNodeType = z.infer<typeof CausalNodeTypeSchema>;
export type CausalNode = z.infer<typeof CausalNodeSchema>;
export type CausalEdge = z.infer<typeof CausalEdgeSchema>;
export type CausalTree = z.infer<typeof CausalTreeSchema>;
