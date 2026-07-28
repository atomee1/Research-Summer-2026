"use client";

import { useMemo, useState } from "react";
import type { CausalTree } from "@/lib/schema";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type Props = {
  title: string;
  articleText: string;
  causalTree: CausalTree;
};

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

export function ResearchChat({ title, articleText, causalTree }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "I can help turn the causal tree’s reporting gaps into concrete research steps. Ask about a weak causal link, a blind spot, a source to contact, or what evidence would strengthen the story.",
    },
  ]);

  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);

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
        }),
      });

      const text = await response.text();

      let data: { reply?: string; error?: string };

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
          article and causal tree as context; it does not browse the web.
        </p>
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
            <p className="whitespace-pre-wrap">{message.content}</p>
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
