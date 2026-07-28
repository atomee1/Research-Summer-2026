"use client";

import { useState } from "react";

import sampleArticlesRaw from "@/data/examples/sampleArticles.json";
import { CausalFramingPanel } from "@/components/CausalFramingPanel";
import { CausalTreeGraph } from "@/components/CausalTreeGraph";
import { ExportJsonButton } from "@/components/ExportJsonButton";
import type { CausalTree, SchemaCard } from "@/lib/schema";
import { ResearchChat } from "@/components/ResearchChat";

type ExampleArticle = {
  id: string;
  title: string;
  date?: string;
  category?: string;
  url?: string;
  text: string;
};

const sampleArticles = sampleArticlesRaw as ExampleArticle[];

async function readJsonResponse(response: Response) {
  const text = await response.text();

  try {
    return JSON.parse(text);
  } catch {
    throw new Error(
      `Server returned non-JSON response. Status: ${response.status}. Preview: ${text.slice(
        0,
        200
      )}`
    );
  }
}

function makeDownloadFilename(title: string) {
  const base = title || "article";

  return `${base}-causal-tree.json`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export default function Home() {
  const [selectedExampleId, setSelectedExampleId] = useState("");
  const [title, setTitle] = useState("");
  const [articleText, setArticleText] = useState("");

  const [generatedSchema, setGeneratedSchema] = useState<SchemaCard | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);

  const [causalTree, setCausalTree] = useState<CausalTree | null>(null);
  const [causalLoading, setCausalLoading] = useState(false);

  const [chatDraftPrompt, setChatDraftPrompt] = useState<string | null>(null);

  function loadExample(exampleId: string) {
    setSelectedExampleId(exampleId);

    const example = sampleArticles.find((article) => article.id === exampleId);

    if (!example) {
      return;
    }

    setTitle(example.title);
    setArticleText(example.text);
    setGeneratedSchema(null);
    setCausalTree(null);
  }

  async function extractSchema() {
    setSchemaLoading(true);
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

      const data = await readJsonResponse(response);

      if (!response.ok) {
        throw new Error(data.error ?? "Schema extraction failed.");
      }

      setGeneratedSchema(data.schema);
    } catch (error) {
      alert(error instanceof Error ? error.message : "Unknown error.");
    } finally {
      setSchemaLoading(false);
    }
  }

  async function extractCausalTree() {
    setCausalLoading(true);
    setCausalTree(null);

    try {
      const response = await fetch("/api/extract-causal-tree", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title,
          text: articleText,
        }),
      });

      const data = await readJsonResponse(response);

      if (!response.ok) {
        throw new Error(data.error ?? "Causal tree extraction failed.");
      }

      setCausalTree(data.tree);
    } catch (error) {
      alert(error instanceof Error ? error.message : "Unknown error.");
    } finally {
      setCausalLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8">
          <p className="text-sm font-medium uppercase tracking-wide text-purple-300">
            Research prototype
          </p>

          <h1 className="mt-2 text-3xl font-bold">
            Causal Lens
          </h1>

          <p className="mt-2 max-w-3xl text-slate-300">
            Extract causal trees from news articles, inspect how strongly the article supports each causal
            link, and surface reporting gaps for further investigation.
          </p>
        </header>

        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="flex-1">
              <label className="block text-sm font-medium text-slate-300">
                Load example article
              </label>

              <select
                className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-slate-100"
                value={selectedExampleId}
                onChange={(event) => loadExample(event.target.value)}
              >
                <option value="">Choose an example...</option>

                {sampleArticles.map((article) => (
                  <option key={article.id} value={article.id}>
                    {article.title}
                    {article.category ? ` — ${article.category}` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="text-sm text-slate-400">
              ...or paste your own article below.
            </div>
          </div>

          <div className="mt-5">
            <label className="block text-sm font-medium text-slate-300">
              Article title
            </label>

            <input
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-slate-100"
              placeholder="Article title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>

          <div className="mt-4">
            <label className="block text-sm font-medium text-slate-300">
              Article text
            </label>

            <textarea
              className="mt-2 h-64 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-slate-100"
              placeholder="Paste article text here"
              value={articleText}
              onChange={(event) => setArticleText(event.target.value)}
            />
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              className="rounded-lg bg-purple-500 px-4 py-2 font-medium text-white disabled:opacity-50"
              onClick={extractCausalTree}
              disabled={causalLoading || !title.trim() || !articleText.trim()}
            >
              {causalLoading ? "Extracting causal tree..." : "Extract causal tree"}
            </button>

            <button
              className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 font-medium text-slate-100 disabled:opacity-50"
              onClick={extractSchema}
              disabled={schemaLoading || !title.trim() || !articleText.trim()}
            >
              {schemaLoading ? "Extracting schema..." : "Extract basic schema"}
            </button>
          </div>
        </section>

        {generatedSchema && (
          <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-5">
            <h2 className="text-xl font-semibold">Basic schema</h2>

            <p className="mt-2 text-sm text-slate-400">
              This is the older schema extraction output. It is still useful for
              debugging and comparison, but causal analysis is now the main tool.
            </p>

            <pre className="mt-4 overflow-x-auto rounded-lg bg-slate-950 p-4 text-sm text-slate-300">
              {JSON.stringify(generatedSchema, null, 2)}
            </pre>
          </section>
        )}

        {causalTree && (
          <>
            <CausalFramingPanel tree={causalTree} />

            <div className="mt-4">
              <ExportJsonButton
                data={causalTree}
                filename={makeDownloadFilename(title)}
              />
            </div>

            <CausalTreeGraph
              tree={causalTree}
              onAskAssistant={(prompt) => setChatDraftPrompt(prompt)}
            />

            <ResearchChat
              title={title}
              articleText={articleText}
              causalTree={causalTree}
              draftPrompt={chatDraftPrompt}
              onDraftPromptConsumed={() => setChatDraftPrompt(null)}
            />
          </>
        )}
      </div>
    </main>
  );
}
