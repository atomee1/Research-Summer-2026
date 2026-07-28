import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

import json

import pandas as pd
import streamlit as st

from src.analogy_search import find_analogies
from src.llm_client import critique_schema, debate_reply, fix_field, get_client, get_model
from src.schema_models import LIST_FIELDS, SchemaCard

FIELD_LABELS = {
    "headline": "Headline",
    "topic": "Topic",
    "story_type": "Story type",
    "trigger_event": "Trigger event",
    "central_conflict": "Central conflict",
    "main_actors": "Main actors",
    "affected_group": "Affected group",
    "stakes": "Stakes",
    "causal_chain": "Causal chain",
    "narrative_schema": "Narrative schema",
    "analogy_signature": "Analogy signature",
    "missing_information_a_reporter_might_seek": "Missing information a reporter might seek",
}
FIELD_ORDER = list(FIELD_LABELS.keys())


def load_jsonl(path: str) -> list[dict]:
    records = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def save_jsonl(path: str, records: list[dict]) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_articles_by_id(path: str) -> dict[str, str]:
    if not Path(path).exists():
        return {}
    df = pd.read_csv(path)
    return {str(row["id"]): str(row["text"]) for _, row in df.iterrows()}


def widget_key(article_id: str, field: str) -> str:
    return f"field::{article_id}::{field}"


def apply_fix(article_id: str, field: str, schema: dict, article_title: str, article_text: str, instruction: str = "") -> None:
    if not article_text:
        st.error("No source article text found for this id in data/sample_articles.csv -- can't ground an AI fix.")
        return
    try:
        client = get_client()
        model = get_model()
        new_value = fix_field(
            client, model, field, schema.get(field), article_title, article_text, schema, instruction=instruction,
        )
    except Exception as e:
        st.error(f"Fix failed: {e}")
        return
    st.session_state[widget_key(article_id, field)] = "\n".join(new_value) if field in LIST_FIELDS else new_value
    st.rerun()


def render_field(article_id: str, schema: dict, field: str, article_title: str, article_text: str) -> None:
    label = FIELD_LABELS[field]
    key = widget_key(article_id, field)
    is_list = field in LIST_FIELDS

    if key not in st.session_state:
        raw = schema.get(field, [] if is_list else "")
        st.session_state[key] = "\n".join(raw) if is_list else raw

    col1, col2 = st.columns([6, 1])
    with col1:
        height = 100 if (is_list or field in ("central_conflict", "stakes", "narrative_schema", "trigger_event")) else 34
        st.text_area(label + (" (one per line)" if is_list else ""), key=key, height=height)
    with col2:
        st.write("")
        st.write("")
        if st.button("Fix", key=f"fixbtn::{key}", help=f"Ask AI to rewrite '{label}' using the article as ground truth"):
            instruction = st.session_state.get("fix_instruction", "")
            apply_fix(article_id, field, schema, article_title, article_text, instruction=instruction)

    value = st.session_state[key]
    schema[field] = [line.strip() for line in value.split("\n") if line.strip()] if is_list else value


st.set_page_config(page_title="Wikinews Schema Explorer", layout="wide")

st.title("Wikinews Schema + Analogy Explorer")

schema_path = "data/schema_cards.jsonl"
articles_path = "data/sample_articles.csv"

if not Path(schema_path).exists():
    st.error("No schema cards found. Run: python -m src.extract_schema")
    st.stop()

if "records" not in st.session_state:
    st.session_state.records = load_jsonl(schema_path)
if "articles_by_id" not in st.session_state:
    st.session_state.articles_by_id = load_articles_by_id(articles_path)
if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {}
if "critiques" not in st.session_state:
    st.session_state.critiques = {}

records = st.session_state.records
articles_by_id = st.session_state.articles_by_id

article_options = {f"{r['id']} — {r['title']}": str(r["id"]) for r in records}

selected_label = st.selectbox("Choose an article", list(article_options.keys()))
query_id = article_options[selected_label]

prefer_cross_topic = st.checkbox("Prefer cross-topic analogies", value=True)
top_k = st.slider("Number of analogies", min_value=1, max_value=10, value=5)

query_record = next(r for r in records if str(r["id"]) == query_id)
schema = query_record["schema"]
article_title = query_record["title"]
article_text = articles_by_id.get(query_id, "")

if not article_text:
    st.warning(
        f"No source text found for article id {query_id} in {articles_path}. "
        "The AI fixer, critique bot, and chat need the source article and will be disabled."
    )

tab_explorer, tab_chat = st.tabs(["Schema Explorer", "Journalist Chat (Advocate vs. Skeptic)"])

with tab_explorer:
    left, right = st.columns([1, 1])

    with left:
        st.subheader("Schema Card")
        st.text_input(
            "Optional instruction for the next AI fix (e.g. 'be more specific about who is affected')",
            key="fix_instruction",
        )

        for field in FIELD_ORDER:
            render_field(query_id, schema, field, article_title, article_text)

        save_col, _ = st.columns([1, 3])
        with save_col:
            if st.button("Save changes to schema_cards.jsonl"):
                save_jsonl(schema_path, records)
                st.success("Saved.")

        st.divider()
        st.subheader("Critique Bot")
        st.caption("Reviews this schema against the source article for vague, unsupported, or missing content.")

        if st.button("Run critique", disabled=not article_text):
            try:
                client = get_client()
                model = get_model()
                st.session_state.critiques[query_id] = critique_schema(client, model, article_title, article_text, schema)
            except Exception as e:
                st.error(f"Critique failed: {e}")

        critique = st.session_state.critiques.get(query_id)
        if critique:
            st.info(critique.overall_assessment)
            severity_icon = {"high": "🔴", "medium": "🟠", "low": "🟡"}
            if not critique.issues:
                st.write("No issues flagged.")
            for i, issue in enumerate(critique.issues):
                icon = severity_icon.get(issue.severity.lower(), "⚪")
                with st.expander(f"{icon} {FIELD_LABELS.get(issue.field, issue.field)}: {issue.issue[:70]}"):
                    st.write(f"**Issue:** {issue.issue}")
                    st.write(f"**Suggested fix:** {issue.suggestion}")
                    if issue.field in schema and st.button("Apply suggestion", key=f"apply::{query_id}::{issue.field}::{i}"):
                        apply_fix(query_id, issue.field, schema, article_title, article_text, instruction=issue.suggestion)

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

with tab_chat:
    st.subheader(f"Journalist Chat — {article_title}")
    st.caption(
        "Ask a question about this story. Two AI personas answer from the same evidence: "
        "an Advocate who defends the article's framing, and a Skeptic who challenges it -- "
        "opposing readings trained against each other like a GAN, so you can stress-test your angle."
    )

    history = st.session_state.chat_histories.setdefault(query_id, [])

    for turn in history:
        with st.chat_message("user"):
            st.write(turn["question"])
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🟢 Advocate**")
            st.write(turn["advocate"])
        with col2:
            st.markdown("**🔴 Skeptic**")
            st.write(turn["skeptic"])
        st.divider()

    question = st.chat_input("Ask a question about this story...", disabled=not article_text)
    if question:
        try:
            client = get_client()
            model = get_model()
            reply = debate_reply(client, model, article_title, article_text, schema, history, question)
            history.append({"question": question, "advocate": reply.advocate, "skeptic": reply.skeptic})
            st.rerun()
        except Exception as e:
            st.error(f"Chat failed: {e}")

    if history and st.button("Clear conversation"):
        st.session_state.chat_histories[query_id] = []
        st.rerun()
