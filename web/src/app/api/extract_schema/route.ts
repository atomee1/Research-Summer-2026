import OpenAI from "openai";
import { zodTextFormat } from "openai/helpers/zod";
import { SchemaCardSchema } from "@/lib/schema";

export const runtime = "nodejs";

const SYSTEM_PROMPT = `
You are helping build a research tool for journalism.

Your job is to extract a reusable narrative schema from a news article.
Do not merely summarize the topic. Focus on the deeper structure of the story.

A useful schema should help someone find analogies across different topics.
For example, a story about a hospital closing and a story about a school closing
may share a deeper structure: an essential public service is reduced because of
institutional constraints, harming a dependent community and raising accountability questions.

Return a structured schema card.
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

  const model = process.env.OPENAI_MODEL ?? "gpt-5.4-mini";

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
      format: zodTextFormat(SchemaCardSchema, "schema_card"),
    },
  });

  return Response.json({
    schema: response.output_parsed,
  });
}
