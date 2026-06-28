import type { ArticleRecord } from "./schema";

const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "but", "if", "then", "of", "to", "in", "on",
  "for", "with", "by", "from", "as", "at", "is", "are", "was", "were", "be",
  "been", "being", "this", "that", "these", "those", "it", "its", "their",
  "his", "her", "they", "them", "he", "she", "we", "you", "about", "into",
]);

function schemaText(record: ArticleRecord): string {
  const s = record.schema;

  return [
    s.story_type,
    s.trigger_event,
    s.central_conflict,
    s.affected_group,
    s.stakes,
    s.causal_chain.join(" "),
    s.narrative_schema,
    s.analogy_signature,
  ].join(" ");
}

function tokenize(text: string): string[] {
  return (
    text
      .toLowerCase()
      .match(/[a-z0-9]+/g)
      ?.filter((token) => token.length > 2 && !STOPWORDS.has(token)) ?? []
  );
}

function termCounts(tokens: string[]): Map<string, number> {
  const counts = new Map<string, number>();

  for (const token of tokens) {
    counts.set(token, (counts.get(token) ?? 0) + 1);
  }

  return counts;
}

function cosineSimilarity(a: Map<string, number>, b: Map<string, number>): number {
  let dot = 0;
  let aNorm = 0;
  let bNorm = 0;

  for (const [term, aValue] of a.entries()) {
    dot += aValue * (b.get(term) ?? 0);
    aNorm += aValue * aValue;
  }

  for (const bValue of b.values()) {
    bNorm += bValue * bValue;
  }

  if (aNorm === 0 || bNorm === 0) return 0;

  return dot / (Math.sqrt(aNorm) * Math.sqrt(bNorm));
}

export function findAnalogies(
  records: ArticleRecord[],
  queryId: string,
  topK = 5,
  preferCrossTopic = true
) {
  const queryRecord = records.find((record) => record.id === queryId);

  if (!queryRecord) {
    throw new Error(`Could not find article id ${queryId}`);
  }

  const queryVector = termCounts(tokenize(schemaText(queryRecord)));
  const queryTopic = queryRecord.schema.topic.toLowerCase().trim();

  return records
    .filter((record) => record.id !== queryId)
    .map((record) => {
      const vector = termCounts(tokenize(schemaText(record)));
      let score = cosineSimilarity(queryVector, vector);

      const candidateTopic = record.schema.topic.toLowerCase().trim();

      if (preferCrossTopic && candidateTopic === queryTopic) {
        score *= 0.75;
      }

      return {
        id: record.id,
        title: record.title,
        topic: record.schema.topic,
        story_type: record.schema.story_type,
        score,
        narrative_schema: record.schema.narrative_schema,
        analogy_signature: record.schema.analogy_signature,
        url: record.url ?? "",
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);
}
