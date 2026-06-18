import argparse
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def load_jsonl(path: str) -> list[dict]:
    records = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def schema_text(record: dict) -> str:
    schema = record["schema"]

    fields = [
        schema.get("story_type", ""),
        schema.get("trigger_event", ""),
        schema.get("central_conflict", ""),
        schema.get("affected_group", ""),
        schema.get("stakes", ""),
        " ".join(schema.get("causal_chain", [])),
        schema.get("narrative_schema", ""),
        schema.get("analogy_signature", ""),
    ]

    return " ".join(fields)

def find_analogies(records: list[dict], query_id: str, top_k: int = 5, prefer_cross_topic: bool = True) -> list[dict]:
    ids = [str(r["id"]) for r in records]

    if query_id not in ids:
        raise ValueError(f"Could not find article id {query_id}. Available ids: {ids}")

    query_index = ids.index(query_id)
    texts = [schema_text(r) for r in records]

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(texts)

    similarities = cosine_similarity(matrix[query_index], matrix).flatten()

    query_topic = records[query_index]["schema"].get("topic", "").lower().strip()

    results = []
    for i, score in enumerate(similarities):
        if i == query_index:
            continue

        record = records[i]
        candidate_topic = record["schema"].get("topic", "").lower().strip()

        adjusted_score = float(score)

        if prefer_cross_topic and candidate_topic == query_topic:
            adjusted_score *= 0.75

        results.append(
            {
                "id": record["id"],
                "title": record["title"],
                "topic": record["schema"].get("topic", ""),
                "story_type": record["schema"].get("story_type", ""),
                "score": round(adjusted_score, 4),
                "narrative_schema": record["schema"].get("narrative_schema", ""),
                "analogy_signature": record["schema"].get("analogy_signature", ""),
                "url": record.get("url", ""),
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schemas", default="data/schema_cards.jsonl")
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--same-topic-ok", action="store_true")
    args = parser.parse_args()

    records = load_jsonl(args.schemas)

    query_record = next(r for r in records if str(r["id"]) == str(args.query_id))

    print("\nQUERY ARTICLE")
    print("-------------")
    print(query_record["title"])
    print(query_record["schema"]["narrative_schema"])

    results = find_analogies(
        records=records,
        query_id=str(args.query_id),
        top_k=args.top_k,
        prefer_cross_topic=not args.same_topic_ok,
    )

    print("\nSTRUCTURAL ANALOGIES")
    print("--------------------")
    for rank, result in enumerate(results, start=1):
        print(f"\n{rank}. {result['title']}")
        print(f"   Topic: {result['topic']}")
        print(f"   Story type: {result['story_type']}")
        print(f"   Score: {result['score']}")
        print(f"   Schema: {result['narrative_schema']}")
        print(f"   Analogy signature: {result['analogy_signature']}")
        if result["url"]:
            print(f"   URL: {result['url']}")

if __name__ == "__main__":
    main()