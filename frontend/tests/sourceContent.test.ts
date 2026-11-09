import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bandTable, extractBands } from "../src/lib/sourceContent.ts";
import { answerForClipboard, numberCitations } from "../src/lib/answerText.ts";
import type { ChatResponse, PolicyPassage } from "../src/lib/api.ts";

const chunks = readFileSync(new URL("../../data/policy_chunks/2026-10-15/chunks.jsonl", import.meta.url), "utf8")
  .trim().split("\n").map((line) => JSON.parse(line));
const chunk = chunks.find((row) => row.chunk_id === "CHUNK_EHG_48");
const source: PolicyPassage = { id: chunk.chunk_id, title: chunk.section_heading, text: chunk.content,
  source_url: chunk.source_url, snapshot_id: chunk.snapshot_date, verified_on: chunk.verified_on,
  effective_date: chunk.effective_date, page_last_updated: chunk.page_last_updated, superseded: false };

const response = (message: string): ChatResponse => ({ status: "answered", route: "policy", mode: "snapshot",
  message, citations: [source], price_result: null, suggestions: [], trace: [], retrieval_rounds: 1 });

test("actual split PDF header identifies half-income and non-resident spouse scope", () => {
  const bands = extractBands(source.text)!;
  assert.equal(bands.incomeBasis, "half_household");
  assert.equal(bands.title, "Half of average monthly household income");
  assert.equal(bands.scope, "Applicant with non-resident spouse");
  // Check every row against the committed source, not generated estimates.
  const expected = source.text.split("\n").filter((line) => /^(Not more than \$|\$[\d,]+ to \$)/.test(line));
  assert.equal(bands.bands.length, expected.length);
  assert.deepEqual(bandTable(bands).rows.map((row) => row.join(" ")), expected);
  assert.deepEqual(bandTable(bands).rows[0], ["Not more than $750", "$60,000"]);
  assert.deepEqual(bandTable(bands).rows.at(-1), ["$4,251 to $4,500", "$2,500"]);
});

test("mixed-couple source retains its distinct scope", () => {
  const family = chunks.find((row) => row.chunk_id === "CHUNK_EHG_46");
  const bands = extractBands(family.content)!;
  assert.equal(bands.incomeBasis, "half_household");
  assert.equal(bands.scope, "Couple comprising a first-timer and second-timer");
});

test("ordinary source headers remain full-household income", () => {
  const bands = extractBands(source.text.replace("Half of the average monthly household\nEHG amount\nincome",
    "Average monthly household income EHG amount"))!;
  assert.equal(bands.incomeBasis, "household");
});

test("unknown basis does not silently become household income", () => {
  const bands = extractBands(extractBands(source.text)!.sourceRows.join("\n"))!;
  assert.equal(bands.incomeBasis, "unknown");
});

test("overlapping or multiple separate band tables are not combined into a graph", () => {
  assert.equal(extractBands(source.text.replace("$751 to $1,000", "$700 to $1,000")), null);
  assert.equal(extractBands(source.text + "\n\nDifferent source table\n" + extractBands(source.text)!.sourceRows.join("\n")), null);
});

test("a complete flattened source block becomes a table and keeps surrounding conditions and citation", () => {
  const bands = extractBands(source.text)!;
  const message = `Other conditions still apply.\n\n${bands.sourceHeader.replace(/\n/g, " ")} ${bands.sourceRows.join(" ")} [${source.id}]`;
  const formatted = numberCitations(response(message));
  assert.match(formatted, /Other conditions still apply/);
  assert.match(formatted, /\| Half of average monthly household income \| Grant amount \(SGD\) \|/);
  assert.match(formatted, /\| \$4,251 to \$4,500 \| \$2,500 \|/);
  assert.match(formatted, /\[1\]/);
  assert.doesNotMatch(formatted, /Your (band|grant)|you (receive|get)/i);
  const copy = answerForClipboard(response(message));
  assert.ok(copy.includes(source.source_url));
  assert.ok(copy.includes("| Not more than $750 | $60,000 |"));
});

test("partial, altered or uncited number lists are never reconstructed as a complete source table", () => {
  const bands = extractBands(source.text)!;
  const partial = bands.sourceRows.slice(0, 4).join(" ") + ` [${source.id}]`;
  assert.doesNotMatch(numberCitations(response(partial)), /\| --- \|/);
  const altered = bands.sourceRows.join(" ").replace("$60,000", "$61,000") + ` [${source.id}]`;
  assert.doesNotMatch(numberCitations(response(altered)), /\| --- \|/);
  assert.doesNotMatch(numberCitations(response(bands.sourceRows.join(" "))), /\| --- \|/);
  const extraDigits = bands.sourceRows.join(" ") + `,000 [${source.id}]`;
  assert.doesNotMatch(numberCitations(response(extraDigits)), /\| --- \|/);
});
