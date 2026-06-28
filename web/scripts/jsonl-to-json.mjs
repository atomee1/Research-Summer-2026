import fs from "node:fs";
import path from "node:path";

const inputPath = path.join(process.cwd(), "..", "data", "schema_cards.jsonl");
const outputDir = path.join(process.cwd(), "src", "data");
const outputPath = path.join(outputDir, "schemaCards.json");

if (!fs.existsSync(inputPath)) {
  console.error(`Could not find input file: ${inputPath}`);
  process.exit(1);
}

const lines = fs
  .readFileSync(inputPath, "utf-8")
  .split("\n")
  .filter(Boolean);

const records = lines.map((line) => JSON.parse(line));

fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(outputPath, JSON.stringify(records, null, 2));

console.log(`Wrote ${records.length} records to ${outputPath}`);
