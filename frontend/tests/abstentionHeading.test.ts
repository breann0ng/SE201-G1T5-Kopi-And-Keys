import { test } from "node:test";
import assert from "node:assert/strict";
import { abstentionHeading } from "../src/lib/abstentionHeading.ts";

test("no matching sales and uncovered periods have informational headings", () => {
  assert.equal(abstentionHeading({ trace: ["abstention:no_transactions"] }), "No matching resale transactions");
  assert.equal(abstentionHeading({ trace: ["abstention:price_out_of_range"] }), "No resale data for that period");
});

test("profile scope and verification failures retain distinct explanations", () => {
  assert.match(abstentionHeading({ trace: ["abstention:profile_scope"] }), /assess this profile/);
  assert.equal(abstentionHeading({ trace: ["verifier:failed", "abstention:verification_failed"] }),
    "I can't answer this reliably from official sources");
});
