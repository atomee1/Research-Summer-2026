import OpenAI from "openai";

export const runtime = "nodejs";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const SYSTEM_PROMPT = `
You are a research assistant for journalists using a causal-analysis tool.

Your job is to help the journalist investigate reporting gaps, weak causal links,
alternative explanations, and next research steps.

Important rules:
- You do not have web browsing unless external sources are provided by the user.
- Do not invent facts, documents, quotes, statistics, or source claims.
- Use the provided article text and causal-tree analysis as your main context.
- When a reporting gap cannot be filled from the article, say so clearly.
- Help the journalist figure out HOW to fill the gap.
- Suggest source types, documents, interview targets, search terms, public records, and verification questions.
- Distinguish between what the article explicitly reports, what it implies, and what remains unknown.
- Be concrete and practical.
- When relevant, explain how new evidence would affect the causal tree or article support score.

When answering questions about a reporting gap or causal link, prefer this structure:

1. What the article currently supports
2. What remains unknown
3. Sources or documents to seek
4. Interview questions
5. Search terms
6. How this evidence could change the causal tree
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

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const title = String(body.title ?? "");
    const articleText = String(body.articleText ?? "");
    const causalTree = body.causalTree ?? null;
    const messages = (body.messages ?? []) as ChatMessage[];

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
