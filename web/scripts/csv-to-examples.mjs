import fs from "node:fs";
import path from "node:path";
import { parse } from "csv-parse/sync";

const inputPath = path.join(process.cwd(), "src", "data", "sample_articles.csv");
const outputDir = path.join(process.cwd(), "src", "data", "examples");
const outputPath = path.join(outputDir, "sampleArticles.json");

if (!fs.existsSync(inputPath)) {
  console.error(`Could not find CSV file: ${inputPath}`);
  process.exit(1);
}

const csvText = fs.readFileSync(inputPath, "utf-8");

const records = parse(csvText, {
  columns: true,
  skip_empty_lines: true,
  trim: true,
});

const examples = records.map((row, index) => ({
  id: String(row.id || index + 1),
  title: String(row.title || "Untitled article"),
  date: String(row.date || ""),
  category: String(row.category || ""),
  url: String(row.url || ""),
  text: String(row.text || ""),
}));

fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(outputPath, JSON.stringify(examples, null, 2), "utf-8");

console.log(`Wrote ${examples.length} example articles to ${outputPath}`);
