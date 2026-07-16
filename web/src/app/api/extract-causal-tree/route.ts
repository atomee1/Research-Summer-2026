import OpenAI from "openai";
import { zodTextFormat } from "openai/helpers/zod";
import { CausalTreeSchema } from "@/lib/schema";

export const runtime = "nodejs";

const SYSTEM_PROMPT = `
You are helping build a research tool for journalism.

Your task is to extract a causal tree and causal framing analysis from a news article.

The goal is not to determine objective truth. The goal is to model how the article's narrative explains events, assigns responsibility, implies causes, and leaves uncertainties.

Important rules:
- Identify the central event or outcome the article is trying to explain.
- Build a causal tree, not just a linear chain.
- For each important event, identify 1-3 possible causes or contributing factors.
- A cause can itself have causes.
- Use only the article text and reasonable inferences from the article's narrative.
- Do not invent facts.
- Do not treat an attributed claim as objective fact.
- The support_score is NOT real-world probability. It means how strongly the article supports that causal link.
- Mark whether each causal link is explicitly reported, attributed to a source, strongly implied, weakly implied, disputed, background context, or unsupported hypothesis.
- For weak, speculative, disputed, or merely implied links, generate concrete reporting questions a journalist should ask next.
- Also identify the article's dominant causal explanation: what does the article seem to foreground as the main reason the central event happened?
- Identify foregrounded causes, backgrounded causes, alternative explanations, possible blind spots, and a compact causal signature.

Think like an editor:
- What does the article make the reader think caused the event?
- What evidence supports that explanation?
- What causal claims are merely implied?
- What is missing that a reporter would need to verify?
- What accountability angle is foregrounded or hidden?

Support score rubric:
- 0.85-1.00: The article explicitly reports the causal link, or multiple pieces of article evidence strongly support it.
- 0.65-0.84: The article strongly implies the causal link, but does not fully establish it.
- 0.40-0.64: The article suggests the link through sequence, framing, or attribution, but evidence is limited.
- 0.20-0.39: The link is weak, speculative, contested, or mostly background context.
- 0.00-0.19: The link is barely supported and should usually be avoided unless clearly marked as a hypothesis.

Do not use support_score as real-world probability.
Do not assign high support to a causal link merely because it sounds plausible.
High support requires clear evidence in the article.
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
