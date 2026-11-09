import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import type { ThreadMessage } from "@assistant-ui/react";
import { changeChat, currentChatId, deleteChat, loadChat, openChat, saveChat, startNewChat, summaries } from "../src/lib/history.ts";

const values = new Map<string, string>();
Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
  getItem: (key: string) => values.get(key) ?? null,
  setItem: (key: string, value: string) => values.set(key, value),
} });
beforeEach(() => values.clear());

function message(text: string): ThreadMessage {
  return { id: text, role: "user", content: [{ type: "text", text }],
    metadata: { custom: {} } } as ThreadMessage;
}

test("New chat is selected with its own title while the earlier conversation stays saved", () => {
  const old = currentChatId();
  saveChat([message("Can EHG and PHG be combined?")]);
  const storedBefore = values.get("kk:chats");
  startNewChat();
  const fresh = currentChatId();
  assert.notEqual(fresh, old);
  assert.deepEqual(loadChat(), []);
  assert.deepEqual(summaries()[0], { id: fresh, title: "New chat", updated: 0 });
  assert.equal(summaries().find((c) => c.id === old)?.title, "Can EHG and PHG be combined?");
  assert.equal(values.get("kk:chats"), storedBefore);
});

test("first sent question names only the new chat; opening the old chat restores its messages", () => {
  const old = currentChatId(); saveChat([message("Old question")]);
  startNewChat(); const fresh = currentChatId();
  saveChat([message("New loan question")]);
  assert.equal(summaries().find((c) => c.id === fresh)?.title, "New loan question");
  assert.equal(openChat(old)[0].content, "Old question");
  assert.equal(currentChatId(), old);
  assert.equal(summaries().find((c) => c.id === old)?.title, "Old question");
});

test("reset notifications cannot copy old messages into the new chat and the composer clears", () => {
  const previous = [message("Earlier question")];
  const old = currentChatId(); saveChat(previous);
  let cancelled = false, draft = "unsent draft", visible = previous;
  const thread = {
    cancelRun() { cancelled = true; saveChat(previous); },
    reset() {
      // Runtime replacement may notify subscribers before its new state is visible.
      saveChat(previous);
      visible = [];
      saveChat(visible);
    },
    composer: { setText(text: string) { draft = text; } },
  };
  changeChat(thread, () => { startNewChat(); return []; });
  assert.equal(cancelled, true);
  assert.equal(draft, "");
  assert.deepEqual(visible, []);
  assert.deepEqual(loadChat(), []);
  assert.equal(summaries()[0].title, "New chat");
  assert.equal(summaries().filter((c) => c.title === "Earlier question").length, 1);
  assert.equal(openChat(old)[0].content, "Earlier question");
});

test("repeated empty New chat clicks do not evict saved conversations or accumulate drafts", () => {
  for (let i = 0; i < 20; i++) { startNewChat(); saveChat([message(`Saved ${i}`)]); }
  for (let i = 0; i < 25; i++) startNewChat();
  assert.equal(summaries().filter((c) => c.title === "New chat").length, 1);
  assert.equal(summaries().length, 21);
  assert.equal(JSON.parse(values.get("kk:chats")!).length, 20);
});

test("deleting the selected conversation selects a fresh New chat and keeps the others", () => {
  const old = currentChatId(); saveChat([message("Keep this chat")]);
  startNewChat(); const removed = currentChatId(); saveChat([message("Delete this chat")]);
  deleteChat(removed);
  assert.notEqual(currentChatId(), removed);
  assert.equal(summaries()[0].title, "New chat");
  assert.equal(summaries().some((c) => c.id === removed), false);
  assert.equal(openChat(old)[0].content, "Keep this chat");
});

test("saving resumes after a failed reset", () => {
  const thread = { cancelRun() {}, reset() { throw new Error("reset failed"); }, composer: { setText() {} } };
  assert.throws(() => changeChat(thread, () => []), /reset failed/);
  saveChat([message("Still saved")]);
  assert.equal(loadChat()[0].content, "Still saved");
});
