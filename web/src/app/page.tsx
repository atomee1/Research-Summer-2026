"use client";

import { useMemo, useState } from "react";
import schemaCardsRaw from "@/data/schemaCards.json";
import type { ArticleRecord, SchemaCard } from "@/lib/schema";
import { findAnalogies } from "@/lib/analogySearch";

const schemaCards = schemaCardsRaw as ArticleRecord[];

export default function Home() {
  const [selectedId, setSelectedId] = useState(schemaCards[0]?.id ?? "");
  const [preferCrossTopic, setPreferCrossTopic] = useState(true);
  const [title, setTitle] = useState("");
  const [articleText, setArticleText] = useState("");
  const [generatedSchema, setGeneratedSchema] = useState<SchemaCard | null>(null);
  const [loading, setLoading] = useState(false);

  const selectedArticle = schemaCards.find((record) => record.id === selectedId);

  const analogies = useMemo(() => {
    if (!selectedId) return [];
    return findAnalogies(schemaCards, selectedId, 5, preferCrossTopic);
  }, [selectedId, preferCrossTopic]);

  async function extractSchema() {
    setLoading(true);
    setGeneratedSchema(null);

    try {
      const response = await fetch("/api/extract-schema", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title,
          text: articleText,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error ?? "Schema extraction failed.");
      }

      setGeneratedSchema(data.schema);
    } catch (error) {
      alert(error instanceof Error ? error.message : "Unknown error.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8">
          <h1 className="text-3xl font-bold">Wikinews Structural Explorer</h1>
          <p className="mt-2 text-slate-300">
            Extract narrative schemas from news stories and find structurally similar articles.
          </p>
        </header>

        <section className="mb-10 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="mb-4 text-xl font-semibold">Explore existing schema cards</h2>

          <label className="block text-sm font-medium text-slate-300">
            Choose article
          </label>

          <select
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-slate-100"
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
          >
            {schemaCards.map((record) => (
              <option key={record.id} value={record.id}>
                {record.id} — {record.title}
              </option>
            ))}
          </select>

          <label className="mt-4 flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={preferCrossTopic}
              onChange={(event) => setPreferCrossTopic(event.target.checked)}
            />
            Prefer cross-topic analogies
          </label>

          {selectedArticle && (
            <div className="mt-6 grid gap-5 md:grid-cols-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
                <h3 className="font-semibold">Schema card</h3>
                <p className="mt-3 text-sm text-slate-400">Topic</p>
                <p>{selectedArticle.schema.topic}</p>

                <p className="mt-3 text-sm text-slate-400">Story type</p>
                <p>{selectedArticle.schema.story_type}</p>

                <p className="mt-3 text-sm text-slate-400">Central conflict</p>
                <p>{selectedArticle.schema.central_conflict}</p>

                <p className="mt-3 text-sm text-slate-400">Narrative schema</p>
                <p>{selectedArticle.schema.narrative_schema}</p>

                <p className="mt-3 text-sm text-slate-400">Analogy signature</p>
                <p className="rounded bg-slate-900 p-2 font-mono text-sm">
                  {selectedArticle.schema.analogy_signature}
                </p>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
                <h3 className="font-semibold">Structural analogies</h3>

                <div className="mt-3 space-y-3">
                  {analogies.map((item) => (
                    <div key={item.id} className="rounded-lg bg-slate-900 p-3">
                      <p className="font-medium">{item.title}</p>
                      <p className="text-sm text-slate-400">
                        Topic: {item.topic} · Score: {item.score.toFixed(3)}
                      </p>
                      <p className="mt-2 text-sm">{item.narrative_schema}</p>
                      <p className="mt-2 rounded bg-slate-950 p-2 font-mono text-xs text-slate-300">
                        {item.analogy_signature}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="mb-4 text-xl font-semibold">Extract a schema from a new article</h2>

          <input
            className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-slate-100"
            placeholder="Article title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />

          <textarea
            className="mt-3 h-48 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-slate-100"
            placeholder="Paste article text here"
            value={articleText}
            onChange={(event) => setArticleText(event.target.value)}
          />

          <button
            className="mt-3 rounded-lg bg-blue-500 px-4 py-2 font-medium text-white disabled:opacity-50"
            onClick={extractSchema}
            disabled={loading}
          >
            {loading ? "Extracting..." : "Extract schema"}
          </button>

          {generatedSchema && (
            <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950 p-4">
              <h3 className="font-semibold">Generated schema</h3>
              <pre className="mt-3 overflow-x-auto text-sm">
                {JSON.stringify(generatedSchema, null, 2)}
              </pre>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
