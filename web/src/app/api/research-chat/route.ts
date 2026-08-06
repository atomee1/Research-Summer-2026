import OpenAI from "openai";

export const runtime = "nodejs";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type WebSource = {
  title: string;
  url: string;
};

const SYSTEM_PROMPT = `
You are a research assistant for journalists using a causal-analysis tool.

Your job is to help the journalist investigate reporting gaps, weak causal links,
alternative explanations, source needs, and next reporting steps.

You do not automatically know facts outside the provided article and causal tree.
Unless web search or external evidence is explicitly provided, do not claim to have verified anything.

Core rules:
- Use the article text and causal-tree analysis as your main context.
- Distinguish between:
  1. what the article explicitly reports,
  2. what the article attributes to a source,
  3. what the article implies,
  4. what remains unknown.
- Do not invent facts, documents, quotes, statistics, source claims, or historical context.
- If the article does not contain enough evidence to answer, say so clearly.
- Be practical and specific, as if helping a reporter plan their next hour of work.
- When discussing a causal link, explain what evidence would strengthen, weaken, or change that link.
- When relevant, explain how new reporting could change the causal tree or article support score.

When answering questions about a reporting gap or causal link, prefer this structure:

1. What the article currently supports
2. What remains unknown
3. Source types to contact
4. Documents/data to look for
5. Interview questions
6. Search terms
7. How new evidence could change the causal tree

Keep answers concrete. Avoid generic advice.
`;

const WEB_RESEARCH_PROMPT = `
Web research is enabled for this response.

Use web search when outside or current evidence would help answer the journalist's
question.

When using web research:
- Clearly distinguish article-derived information from web-derived information.
- Prefer primary sources, official records, government documents, court records,
  original research, direct statements, and reputable reporting.
- Do not claim that finding a source proves a causal relationship.
- Cite factual claims based on web research.
- Explain how the external evidence could strengthen, weaken, complicate, or
  contradict the causal tree.
- Tell the journalist what still requires independent verification.
`;

function formatContext({
  title,
  articleText,
  causalTree,
}: {
  title: string;
  articleText: string;
  causalTree: unknown;
}) {
  return `
ARTICLE TITLE:
${title}

ARTICLE TEXT:
${articleText}

CAUSAL TREE / FRAMING ANALYSIS JSON:
${JSON.stringify(causalTree, null, 2)}
`;
}

function modeInstructions(chatMode: string) {
  switch (chatMode) {
    case "source_strategy":
      return `
Current mode: Source strategy.
Focus on who the journalist should contact, why each source matters, what each source can verify, and what documents or data could corroborate them.
`;

    case "interview_prep":
      return `
Current mode: Interview prep.
Focus on specific interview questions, follow-ups, adversarial questions, and ways to avoid letting sources make unsupported causal claims.
`;

    case "framing_critique":
      return `
Current mode: Framing critique.
Focus on how the article frames responsibility and causality. Identify foregrounded causes, backgrounded causes, missing perspectives, and alternative causal explanations.
`;

    case "reporting_plan":
    default:
      return `
Current mode: Reporting plan.
Focus on practical next steps, evidence needed, gap prioritization, and how new reporting would affect the causal tree.
`;
  }
}

function extractWebSources(response: unknown): WebSource[] {
  const responseObject = response as {
    output?: unknown;
  };

  if (!Array.isArray(responseObject.output)) {
    return [];
  }

  const sources = new Map<string, WebSource>();

  for (const item of responseObject.output) {
    if (typeof item !== "object" || item === null) {
      continue;
    }

    const itemObject = item as {
      type?: unknown;
      content?: unknown;
    };

    if (itemObject.type !== "message" || !Array.isArray(itemObject.content)) {
      continue;
    }

    for (const contentPart of itemObject.content) {
      if (typeof contentPart !== "object" || contentPart === null) {
        continue;
      }

      const contentObject = contentPart as {
        annotations?: unknown;
      };

      if (!Array.isArray(contentObject.annotations)) {
        continue;
      }

      for (const annotation of contentObject.annotations) {
        if (typeof annotation !== "object" || annotation === null) {
          continue;
        }

        const citation = annotation as {
          type?: unknown;
          url?: unknown;
          title?: unknown;
        };

        if (
          citation.type === "url_citation" &&
          typeof citation.url === "string"
        ) {
          sources.set(citation.url, {
            url: citation.url,
            title:
              typeof citation.title === "string"
                ? citation.title
                : citation.url,
          });
        }
      }
    }
  }

  return Array.from(sources.values());
}

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const title = String(body.title ?? "");
    const articleText = String(body.articleText ?? "");
    const causalTree = body.causalTree ?? null;
    const messages = (body.messages ?? []) as ChatMessage[];
    const chatMode = String(body.chatMode ?? "reporting_plan");
    const webEnabled = body.webEnabled === true;

    if (!title.trim() || !articleText.trim()) {
      return Response.json(
        { error: "Missing article title or article text." },
        { status: 400 }
      );
    }

    if (!causalTree) {
      return Response.json(
        { error: "Missing causal tree context." },
        { status: 400 }
      );
    }

    if (!process.env.OPENAI_API_KEY) {
      return Response.json(
        { error: "Missing OPENAI_API_KEY in web/.env.local." },
        { status: 500 }
      );
    }

    const openai = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
    });

    const internalModel = process.env.OPENAI_MODEL ?? "gpt-4o-mini";
    const webModel = process.env.OPENAI_WEB_MODEL ?? "gpt-5.6";

    const model = webEnabled ? webModel : internalModel;

    const context = formatContext({
      title,
      articleText,
      causalTree,
    });

    const webTools = webEnabled
      ? [
          {
            type: "web_search" as const,
            search_context_size: "medium" as const,
          },
        ]
      : undefined;

    const response = await openai.responses.create({
      model,
      tools: webTools,
      tool_choice: webEnabled ? "auto" : undefined,

      input: [
        {
          role: "system",
          content: SYSTEM_PROMPT,
        },
        {
          role: "system",
          content: modeInstructions(chatMode),
        },
        {
          role: "system",
          content: webEnabled
            ? WEB_RESEARCH_PROMPT
            : `
    Web research is disabled.
    Use only the supplied article, causal tree, and conversation.
    Do not imply that you searched for or verified outside information.
    `,
        },
        {
          role: "user",
          content: context,
        },
        ...messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
      ],
    });

    const sources = webEnabled ? extractWebSources(response) : [];

    const usedWeb = response.output.some(
      (item) => item.type === "web_search_call"
    );

    return Response.json({
      reply: response.output_text,
      sources,
      usedWeb,
    });
  } catch (error) {
    console.error("Research chat failed:", error);

    return Response.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unknown research chat error.",
      },
      { status: 500 }
    );
  }
}
