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
