"use client";

import { useEffect, useMemo, useState } from "react";
import type { CausalTree } from "@/lib/schema";

type WebSource = {
  title: string;
  url: string;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  sources?: WebSource[];
  usedWeb?: boolean;
};

type Props = {
  title: string;
  articleText: string;
  causalTree: CausalTree;
  draftPrompt?: string | null;
  onDraftPromptConsumed?: () => void;
};

const QUICK_ACTIONS = [
  {
    label: "Source plan",
    prompt:
      "Create a source plan for investigating the most important reporting gaps in this causal tree. Group sources by officials, affected people, experts, documents, and data.",
  },
  {
    label: "Interview questions",
    prompt:
      "Generate interview questions for the key sources needed to verify the weakest or most important causal links in this story.",
  },
  {
    label: "Documents/data",
    prompt:
      "What documents, public records, datasets, or evidence should a journalist look for to verify the causal claims in this article?",
  },
  {
    label: "Prioritize gaps",
    prompt:
      "Prioritize the reporting gaps in this causal tree. Which should a journalist investigate first, and why?",
  },
  {
    label: "Challenge framing",
    prompt:
      "Challenge the article's dominant causal explanation. What alternative explanations or accountability angles might be underexplored?",
  },
  {
    label: "Research checklist",
    prompt:
      "Turn the reporting gaps and weak causal links into a concrete reporting checklist.",
  },
];

function collectSuggestedQuestions(tree: CausalTree) {
  const questions = new Set<string>();

  for (const gap of tree.reporting_gaps) {
    questions.add(`How should I investigate this reporting gap: ${gap}`);
  }

  for (const edge of tree.edges) {
    for (const question of edge.reporting_questions ?? []) {
      questions.add(question);
    }
  }

  for (const blindSpot of tree.causal_framing.possible_blind_spots) {
    questions.add(`What research would help evaluate this possible blind spot: ${blindSpot}`);
  }

  return Array.from(questions).slice(0, 6);
}

export function ResearchChat({title, articleText, causalTree, draftPrompt, onDraftPromptConsumed, }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "I can help turn the causal tree’s reporting gaps into concrete research steps. Ask about a weak causal link, a blind spot, a source to contact, or what evidence would strengthen the story.",
    },
  ]);

  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);

  const [chatMode, setChatMode] = useState<
    "reporting_plan" | "source_strategy" | "interview_prep" | "framing_critique"
  >("reporting_plan");

  const [webEnabled, setWebEnabled] = useState(false);

  useEffect(() => {
    if (!draftPrompt) {
      return;
    }

    setInput(draftPrompt);
    onDraftPromptConsumed?.();
  }, [draftPrompt, onDraftPromptConsumed]);

  const suggestedQuestions = useMemo(
    () => collectSuggestedQuestions(causalTree),
    [causalTree]
  );

  async function sendMessage(messageText?: string) {
    const content = (messageText ?? input).trim();

    if (!content) {
      return;
    }

    const nextMessages: ChatMessage[] = [
      ...messages,
      {
        role: "user",
        content,
      },
    ];

    setMessages(nextMessages);
    setInput("");
    setIsSending(true);

    try {
      const response = await fetch("/api/research-chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
        title,
        articleText,
        causalTree,
        messages: nextMessages,
        chatMode,
        webEnabled,
      }),
      });

      const text = await response.text();

      let data: {
        reply?: string;
        error?: string;
        sources?: WebSource[];
        usedWeb?: boolean;
      };

      try {
        data = JSON.parse(text);
      } catch {
        throw new Error(
          `Server returned non-JSON response. Status: ${response.status}. Preview: ${text.slice(
            0,
            200
          )}`
        );
      }

      if (!response.ok) {
        throw new Error(data.error ?? "Research chat failed.");
      }

      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: data.reply ?? "I could not generate a response.",
          sources: data.sources ?? [],
          usedWeb: data.usedWeb ?? false,
        },
      ]);
    } catch (error) {
      alert(error instanceof Error ? error.message : "Unknown chat error.");
      setMessages(messages);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-emerald-300">
          Reporting assistant
        </p>

        <h3 className="mt-1 text-xl font-semibold text-slate-100">
          Investigate reporting gaps
        </h3>

        <p className="mt-2 text-sm text-slate-300">
          Ask the assistant how to verify weak causal links, find sources, design
          interview questions, or fill gaps in the causal account. It uses the
          article and causal tree as context; it does not browse the web. It does
          not verify facts unless you provide evidence or enable web-research mode.
          Treat its output as a research plan, not as confirmed information.
        </p>
      </div>

      <div className="mt-5">
        <label className="block text-sm font-medium text-slate-300">
          Assistant mode
        </label>

        <select
          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100"
          value={chatMode}
          onChange={(event) =>
            setChatMode(
              event.target.value as
                | "reporting_plan"
                | "source_strategy"
                | "interview_prep"
                | "framing_critique"
            )
          }
        >
          <option value="reporting_plan">Reporting plan</option>
          <option value="source_strategy">Source strategy</option>
          <option value="interview_prep">Interview prep</option>
          <option value="framing_critique">Framing critique</option>
        </select>
      </div>

      <div className="mt-4 rounded-lg border border-slate-700 bg-slate-950 p-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-slate-100">
              Web research
            </p>

            <p className="mt-1 text-xs text-slate-400">
              {webEnabled
                ? "The assistant may search for current outside evidence and sources."
                : "The assistant will use only the article and causal analysis."}
            </p>
          </div>

          <button
            type="button"
            aria-pressed={webEnabled}
            onClick={() => setWebEnabled((current) => !current)}
            disabled={isSending}
            className={
              webEnabled
                ? "rounded-full bg-emerald-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                : "rounded-full border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-200 disabled:opacity-50"
            }
          >
            {webEnabled ? "Web on" : "Web off"}
          </button>
        </div>

        {webEnabled && (
          <div className="mt-3 rounded-lg border border-emerald-900 bg-emerald-950 p-3 text-xs text-emerald-100">
            Web results are outside evidence, not automatically verified facts.
            Review the cited sources before using them in reporting.
          </div>
        )}
      </div>

      <div className="mt-5">
        <h4 className="text-sm font-semibold text-slate-200">
          Quick research actions
        </h4>

        <div className="mt-2 flex flex-wrap gap-2">
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action.label}
              onClick={() => sendMessage(action.prompt)}
              disabled={isSending}
              className="rounded-full border border-emerald-800 bg-emerald-950 px-3 py-2 text-left text-xs text-emerald-100 hover:bg-emerald-900 disabled:opacity-50"
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>

      {suggestedQuestions.length > 0 && (
        <div className="mt-5">
          <h4 className="text-sm font-semibold text-slate-200">
            Suggested starting questions
          </h4>

          <div className="mt-2 flex flex-wrap gap-2">
            {suggestedQuestions.map((question) => (
              <button
                key={question}
                onClick={() => sendMessage(question)}
                disabled={isSending}
                className="rounded-full border border-slate-700 bg-slate-950 px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-5 max-h-[520px] space-y-3 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950 p-4">
        {messages.map((message, index) => (
          <div
            key={index}
            className={
              message.role === "user"
                ? "ml-auto max-w-[85%] rounded-lg bg-purple-600 p-3 text-sm text-white"
                : "mr-auto max-w-[85%] rounded-lg bg-slate-800 p-3 text-sm text-slate-100"
            }
          >
            {message.role === "assistant" && message.usedWeb && (
              <div className="mb-2">
                <span className="rounded bg-emerald-950 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-emerald-200">
                  Web researched
                </span>
              </div>
            )}

            <p className="whitespace-pre-wrap">{message.content}</p>

            {message.role === "assistant" &&
              message.sources &&
              message.sources.length > 0 && (
                <div className="mt-4 border-t border-slate-700 pt-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Sources
                  </p>

                  <ul className="mt-2 space-y-2">
                    {message.sources.map((source, sourceIndex) => (
                      <li key={`${source.url}-${sourceIndex}`}>
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-emerald-300 underline decoration-emerald-700 underline-offset-2 hover:text-emerald-200"
                        >
                          {source.title || source.url}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
          </div>
        ))}

        {isSending && (
          <div className="mr-auto max-w-[85%] rounded-lg bg-slate-800 p-3 text-sm text-slate-300">
            Thinking...
          </div>
        )}
      </div>

      <div className="mt-4 flex gap-2">
        <textarea
          className="min-h-20 flex-1 rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100"
          placeholder="Ask how to fill a reporting gap, verify a causal link, find sources, or improve the article..."
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              sendMessage();
            }
          }}
        />

        <button
          onClick={() => sendMessage()}
          disabled={isSending || !input.trim()}
          className="self-stretch rounded-lg bg-emerald-500 px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          Send
        </button>
      </div>

      <p className="mt-2 text-xs text-slate-500">
        Tip: press Ctrl+Enter to send.
      </p>
    </section>
  );
}
