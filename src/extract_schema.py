import argparse
import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from src.schema_models import SchemaCard

SYSTEM_PROMPT = """
You are helping build a research tool for journalism.

Your job is to extract a reusable narrative schema from a news article.
Do not merely summarize the topic. Focus on the deeper structure of the story.

A useful schema should help someone find analogies across different topics.
For example, a story about a hospital closing and a story about a school closing
may share a deeper structure: an essential public service is reduced because of
institutional constraints, harming a dependent community and raising accountability questions.

Return a structured schema card.
"""

def extract_schema(client: OpenAI, model: str, title: str, text: str) -> dict:
    article = f"TITLE: {title}\n\nARTICLE:\n{text}"

    completion = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": article},
        ],
        response_format=SchemaCard,
    )

    parsed = completion.choices[0].message.parsed
    return parsed.model_dump()

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/sample_articles.csv")
    parser.add_argument("--output", default="data/schema_cards.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY. Add it to your .env file.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    input_path = Path(args.input)
    output_path = Path(args.output)

    df = pd.read_csv(input_path)

    if args.limit:
        df = df.head(args.limit)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            article_id = str(row["id"])
            title = str(row["title"])
            text = str(row["text"])

            print(f"Extracting schema for {article_id}: {title}")

            try:
                schema = extract_schema(client, model, title, text)
                record = {
                    "id": article_id,
                    "title": title,
                    "date": row.get("date", ""),
                    "category": row.get("category", ""),
                    "url": row.get("url", ""),
                    "schema": schema,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
            except Exception as e:
                print(f"ERROR on article {article_id}: {e}")

    print(f"Saved schema cards to {output_path}")

if __name__ == "__main__":
    main()