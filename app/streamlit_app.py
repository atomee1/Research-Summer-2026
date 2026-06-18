import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

import json

import streamlit as st

from src.analogy_search import find_analogies

def load_jsonl(path: str) -> list[dict]:
    records = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

st.set_page_config(page_title="Wikinews Schema Explorer", layout="wide")

st.title("Wikinews Schema + Analogy Explorer")

schema_path = "data/schema_cards.jsonl"

if not Path(schema_path).exists():
    st.error("No schema cards found. Run: python -m src.extract_schema")
    st.stop()

records = load_jsonl(schema_path)

article_options = {f"{r['id']} — {r['title']}": str(r["id"]) for r in records}

selected_label = st.selectbox("Choose an article", list(article_options.keys()))
query_id = article_options[selected_label]

prefer_cross_topic = st.checkbox("Prefer cross-topic analogies", value=True)
top_k = st.slider("Number of analogies", min_value=1, max_value=10, value=5)

query_record = next(r for r in records if str(r["id"]) == query_id)
schema = query_record["schema"]

left, right = st.columns([1, 1])

with left:
    st.subheader("Schema Card")
    st.write(f"**Headline:** {schema['headline']}")
    st.write(f"**Topic:** {schema['topic']}")
    st.write(f"**Story type:** {schema['story_type']}")
    st.write(f"**Trigger event:** {schema['trigger_event']}")
    st.write(f"**Central conflict:** {schema['central_conflict']}")
    st.write(f"**Affected group:** {schema['affected_group']}")
    st.write(f"**Stakes:** {schema['stakes']}")

    st.write("**Causal chain:**")
    for step in schema["causal_chain"]:
        st.write(f"- {step}")

    st.write("**Narrative schema:**")
    st.info(schema["narrative_schema"])

    st.write("**Analogy signature:**")
    st.code(schema["analogy_signature"])

with right:
    st.subheader("Structural Analogies")

    results = find_analogies(
        records=records,
        query_id=query_id,
        top_k=top_k,
        prefer_cross_topic=prefer_cross_topic,
    )

    for result in results:
        with st.expander(f"{result['title']} — score {result['score']}"):
            st.write(f"**Topic:** {result['topic']}")
            st.write(f"**Story type:** {result['story_type']}")
            st.write("**Narrative schema:**")
            st.write(result["narrative_schema"])
            st.write("**Analogy signature:**")
            st.code(result["analogy_signature"])
            if result["url"]:
                st.write(result["url"])
