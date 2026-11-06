import { test } from "node:test";
import assert from "node:assert/strict";
import { answerForClipboard } from "../src/lib/answerText.ts";
import type { ChatResponse } from "../src/lib/api.ts";

const response: ChatResponse = {
  status: "answered", mode: "snapshot", route: "policy", message: "Conditional answer. [B] Supporting rule. [A]",
  citations: [
    { id: "B", title: "First source", text: "fixture", source_url: "https://example.test/first",
      snapshot_id: "2026-10-15", verified_on: "2026-10-15", effective_date: null, page_last_updated: null, superseded: false },
    { id: "A", title: "Second source", text: "fixture", source_url: "https://example.test/second",
      snapshot_id: "2026-10-15", verified_on: "2026-10-15", effective_date: "2024-08-20", page_last_updated: null, superseded: false },
  ],
  price_result: null, suggestions: [], retrieval_rounds: 1, trace: [],
};

test("copied citation numbers match their actual source URLs and dates", () => {
  const copy = answerForClipboard(response);
  assert.match(copy, /Conditional answer\. \[1\] Supporting rule\. \[2\]/);
  assert.match(copy, /\[1\] First source\nhttps:\/\/example.test\/first/);
  assert.match(copy, /\[2\] Second source\nhttps:\/\/example.test\/second/);
  assert.match(copy, /Verified: 2026-10-15/);
  assert.match(copy, /Effective: 2024-08-20/);
  assert.doesNotMatch(copy, /\[A\]|\[B\]|Effective: null/);
});

test("income notes retain conditions and their own official source reference", () => {
  const copy = answerForClipboard({ ...response, income_notes: [{
    scheme: "fixture", label: "Fictional ceiling", ceiling: "100", within_ceiling: true,
    message: "Other conditions still apply.", conditions: ["Fictional household condition."],
    source_url: "https://example.test/conditions",
  }] });
  assert.match(copy, /Other conditions still apply/);
  assert.match(copy, /Fictional household condition/);
  assert.match(copy, /https:\/\/example.test\/conditions/);
});

test("overview-only answers retain source references", () => {
  const copy = answerForClipboard({ ...response, message: "Overview", overview: [{
    card_id: "fixture", title: "Fixture topic", quote: "Quoted overview.", citation_id: "A",
  }] });
  assert.match(copy, /Fixture topic: Quoted overview\. \[2\]/);
});

test("synthetic evidence warning survives copy", () => {
  assert.match(answerForClipboard({ ...response, mode: "demo" }), /SYNTHETIC DEMO EVIDENCE/);
});

test("a clarification with no sources does not invent citations", () => {
  assert.equal(answerForClipboard({ ...response, status: "clarifying", message: "Please provide age.", citations: [] }),
    "Please provide age.");
});
