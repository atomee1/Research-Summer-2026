import OpenAI from "openai";

export const runtime = "nodejs";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
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

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const title = String(body.title ?? "");
    const articleText = String(body.articleText ?? "");
    const causalTree = body.causalTree ?? null;
    const messages = (body.messages ?? []) as ChatMessage[];
    const chatMode = String(body.chatMode ?? "reporting_plan");

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

    const model = process.env.OPENAI_MODEL ?? "gpt-4o-mini";

    const context = formatContext({
      title,
      articleText,
      causalTree,
    });

    const response = await openai.responses.create({
      model,
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
          role: "user",
          content: context,
        },
        ...messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
      ],
    });

    return Response.json({
      reply: response.output_text,
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
