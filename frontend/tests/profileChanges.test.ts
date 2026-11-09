import { test } from "node:test";
import assert from "node:assert/strict";
import { AssistantRuntimeImpl, LocalRuntimeCore } from "@assistant-ui/core/internal";
import { ProfileChangeController, isProfileChangeMessage, profileChangeText } from "../src/lib/profileChanges.ts";
import { profileWarnings } from "../src/lib/profileWarnings.ts";
import { toHistory } from "../src/lib/history.ts";
import { createAdvisorAdapter } from "../src/lib/adapter.ts";
import type { BuyerProfile, ChatResponse } from "../src/lib/api.ts";
import type { ChatModelAdapter } from "@assistant-ui/react";

const single: BuyerProfile = { citizenship: "SC_single", household_type: "single", age: null,
  household_income: null, first_timer: null, subsidy_status: null };
const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 10));

test("sidebar structural conflicts warn, while consistent single and missing/young age do not", () => {
  assert.deepEqual(profileWarnings(single), []);
  assert.deepEqual(profileWarnings({ ...single, age: 20 }), []);
  assert.ok(profileWarnings({ ...single, household_type: "couple_family" }).length);
  assert.ok(profileWarnings({ ...single, citizenship: "SC/SC" }).length);
  assert.ok(profileWarnings({ ...single, subsidy_status: "mixed" }).length);
});

test("actual changes produce a value-free notice and unchanged values do not", () => {
  assert.equal(profileChangeText(single, { ...single }), null);
  const text = profileChangeText(single, { ...single, age: 37, household_income: 7123 })!;
  assert.match(text, /age, household income/);
  assert.doesNotMatch(text, /37|7123/);
  assert.match(profileChangeText(single, { ...single, household_type: "couple_family" })!, /selections conflict/);
});

test("profile notice is immediate, coalesced, local-only and makes no model call", async () => {
  let calls = 0, visible: unknown;
  const core = new LocalRuntimeCore({ adapters: { chatModel: { async *run() { calls++; yield {}; } } } }, []);
  const runtime = new AssistantRuntimeImpl(core);
  const controller = new ProfileChangeController(runtime.thread, () => "chat", (value) => { visible = value; }, 0);
  try {
    controller.notify("Profile updated: age.");
    assert.match(JSON.stringify(visible), /Profile updated/);
    controller.notify("Profile updated: age, household type.");
    await tick();
    const messages = runtime.thread.getState().messages;
    assert.equal(messages.length, 1);
    assert.equal(calls, 0);
    assert.ok(isProfileChangeMessage(messages[0]));
    assert.deepEqual(toHistory(messages), []);
    assert.equal(visible, null);
  } finally { controller.dispose(); core.threads.getMainThreadRuntimeCore().detach(); }
});

test("editing the profile during a run does not interrupt or rewrite the answer", async () => {
  let release!: () => void, began!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const started = new Promise<void>((resolve) => { began = resolve; });
  const core = new LocalRuntimeCore({ adapters: { chatModel: { async *run() {
    began(); await gate; yield { content: [{ type: "text" as const, text: "Original answer" }] };
  } } } }, []);
  const runtime = new AssistantRuntimeImpl(core);
  const controller = new ProfileChangeController(runtime.thread, () => "chat", () => {}, 0);
  const unsubscribe = runtime.thread.subscribe(() => controller.onThreadChange());
  try {
    runtime.thread.append("Question"); await started;
    controller.notify("Profile updated: household type."); await tick();
    assert.equal(runtime.thread.getState().isRunning, true);
    assert.equal(runtime.thread.getState().messages.length, 2);
    release(); await tick();
    const messages = runtime.thread.getState().messages;
    assert.match(JSON.stringify(messages), /Original answer/);
    assert.equal(messages.filter(isProfileChangeMessage).length, 1);
    assert.equal(toHistory(messages).length, 2);
  } finally { release(); unsubscribe(); controller.dispose(); core.threads.getMainThreadRuntimeCore().detach(); }
});

test("pending profile notice cannot leak into another conversation", async () => {
  let chat = "old";
  const core = new LocalRuntimeCore({ adapters: { chatModel: { async *run() { yield {}; } } } }, []);
  const runtime = new AssistantRuntimeImpl(core);
  const controller = new ProfileChangeController(runtime.thread, () => chat, () => {}, 0);
  try {
    controller.notify("Profile updated in old chat."); chat = "new";
    runtime.thread.reset([]); controller.onThreadChange(); await tick();
    assert.equal(runtime.thread.getState().messages.length, 0);
  } finally { controller.dispose(); core.threads.getMainThreadRuntimeCore().detach(); }
});

test("a submitted answer uses its profile snapshot; the following question uses the new one", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ profile: BuyerProfile }> = [];
  const response: ChatResponse = { status: "answered", mode: "demo", route: "policy", message: "Fixture",
    citations: [], price_result: null, suggestions: [], retrieval_rounds: 1, trace: [] };
  globalThis.fetch = async (_url, init) => {
    requests.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ response }) + "\n", { headers: { "Content-Type": "application/x-ndjson" } });
  };
  let profile = { ...single, age: 35 };
  const adapter = createAdvisorAdapter(() => profile);
  const args = { messages: [{ role: "user", content: [{ type: "text", text: "Question" }] }], abortSignal: new AbortController().signal } as Parameters<ChatModelAdapter["run"]>[0];
  try {
    const first = adapter.run(args) as AsyncGenerator;
    await first.next(); // progress yield: request profile has already been captured
    profile = { ...single, age: 50 };
    for await (const _ of first) void _;
    for await (const _ of adapter.run(args) as AsyncGenerator) void _;
    assert.equal(requests[0].profile.age, 35);
    assert.equal(requests[1].profile.age, 50);
  } finally { globalThis.fetch = originalFetch; }
});
