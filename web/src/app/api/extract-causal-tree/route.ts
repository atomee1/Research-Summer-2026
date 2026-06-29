import OpenAI from "openai";
import { zodTextFormat } from "openai/helpers/zod";
import { CausalTreeSchema } from "@/lib/schema";

export const runtime = "nodejs";

const SYSTEM_PROMPT = `
You are helping build a research tool for journalism.

Your task is to extract a causal tree from a news article.

Important rules:
- Do not merely summarize the article.
- Identify the central event or outcome the article is trying to explain.
- For each important event, identify 1-3 possible causes or contributing factors.
- A cause can itself have causes, producing a tree rather than a single linear chain.
- Use the article text as your evidence.
- Do not claim that a cause is objectively true unless the article clearly establishes it.
- The support_score is NOT real-world probability. It means how strongly the article supports the causal link.
- Prefer explicit reporting over speculation.
- If the article only implies a causal link, mark it as weakly_implied or strongly_implied.
- If a causal claim is attributed to a source, official, critic, or stakeholder, say so in the rationale.
- Include reporting gaps: what would a journalist need to verify next?

Good causal edges look like:
- "budget shortfall" -> "hospital closes"
- "severe storm" -> "transportation delays"
- "new policy" -> "public backlash"
- "lack of staffing" -> "service reduction"

Bad causal edges:
- vague concepts with no article support
- invented background causes not mentioned or implied by the article
- treating political claims as facts without attribution
`;

export async function POST(request: Request) {
  const body = await request.json();

  const title = String(body.title ?? "");
  const text = String(body.text ?? "");

  if (!title.trim() || !text.trim()) {
    return Response.json(
      { error: "Both title and text are required." },
      { status: 400 }
    );
  }

  if (!process.env.OPENAI_API_KEY) {
    return Response.json(
      { error: "Missing OPENAI_API_KEY in .env.local." },
      { status: 500 }
    );
  }

  const openai = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY,
  });

  const model = process.env.OPENAI_MODEL ?? "gpt-4o-mini";

  const response = await openai.responses.parse({
    model,
    input: [
      {
        role: "system",
        content: SYSTEM_PROMPT,
      },
      {
        role: "user",
        content: `TITLE: ${title}\n\nARTICLE:\n${text}`,
      },
    ],
    text: {
      format: zodTextFormat(CausalTreeSchema, "causal_tree"),
    },
  });

  return Response.json({
    tree: response.output_parsed,
  });
}
