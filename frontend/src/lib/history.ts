import type { ThreadMessage, ThreadMessageLike } from "@assistant-ui/react";
import { load, save } from "./storage";

/**
 * Conversation memory, frontend half (option A in the team discussion).
 *
 * The backend accepts recent turns as context, never as policy evidence.
 * Set VITE_SEND_HISTORY=false to disable sending recent turns.
 */
export const SEND_HISTORY = import.meta.env.VITE_SEND_HISTORY !== "false";

/** Previous turns sent to the model. Kept small for the local model's context window. */
export const MAX_HISTORY_MESSAGES = 12;

export type HistoryTurn = { role: "user" | "assistant"; content: string };

const textOf = (m: ThreadMessage) =>
  m.content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("\n")
    .trim();

/** Earlier turns (excluding the message being sent now), oldest first. */
export function toHistory(earlier: readonly ThreadMessage[]): HistoryTurn[] {
  return earlier
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ role: m.role as "user" | "assistant", content: textOf(m).slice(0, 12000) }))
    .filter((t) => t.content)
    .slice(-MAX_HISTORY_MESSAGES);
}

// ---- Saving conversations in this browser (survive reloads; listed under "Recent chats") ----
// Added 2026-10-17 (Sandra): several conversations are kept, not just the current one.
// Each is stored whole; nothing here is sent to the backend except the recent turns above.

export type SavedChat = { id: string; title: string; updated: number; messages: ThreadMessageLike[] };
export type ChatSummary = Pick<SavedChat, "id" | "title" | "updated">;

const CHATS_KEY = "kk:chats";
const CURRENT_KEY = "kk:chat-id";
const LEGACY_KEY = "kk:chat";
const MAX_SAVED_MESSAGES = 60;
const MAX_SAVED_CHATS = 20;

const newId = () => `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

function loadChats(): SavedChat[] {
  const chats = load<SavedChat[]>(CHATS_KEY, []);
  const legacy = load<ThreadMessageLike[]>(LEGACY_KEY, []);
  if (legacy.length && !chats.length) {
    // One-off move of the single chat saved by earlier versions.
    const id = newId();
    chats.push({ id, title: titleOf(legacy), updated: Date.now(), messages: legacy });
    save(CHATS_KEY, chats);
    save(CURRENT_KEY, id);
    save(LEGACY_KEY, []);
  }
  return chats;
}

function titleOf(messages: readonly ThreadMessageLike[]): string {
  const first = messages.find((m) => m.role === "user");
  const content = first?.content;
  const text = typeof content === "string" ? content
    : Array.isArray(content) ? content.map((p) => ("text" in p ? p.text : "")).join(" ") : "";
  const line = text.replace(/\s+/g, " ").trim();
  return line ? (line.length > 48 ? `${line.slice(0, 47)}…` : line) : "New chat";
}

export const summaries = (chats = loadChats()): ChatSummary[] =>
  chats.filter((c) => c.messages.length)
    .sort((a, b) => b.updated - a.updated)
    .map(({ id, title, updated }) => ({ id, title, updated }));

export function currentChatId(): string {
  const id = load<string | null>(CURRENT_KEY, null);
  if (id) return id;
  const fresh = newId();
  save(CURRENT_KEY, fresh);
  return fresh;
}

/** Messages of the current chat, for the runtime's first render. */
export function loadChat(): ThreadMessageLike[] {
  const id = currentChatId();
  return loadChats().find((c) => c.id === id)?.messages ?? [];
}

export function openChat(id: string): ThreadMessageLike[] {
  save(CURRENT_KEY, id);
  return loadChats().find((c) => c.id === id)?.messages ?? [];
}

export function saveChat(messages: readonly ThreadMessage[]): void {
  const done = messages.filter((m) => m.status?.type !== "running");
  if (!done.length) return;
  const id = currentChatId();
  const saved: ThreadMessageLike[] = done.slice(-MAX_SAVED_MESSAGES).map(
    (m): ThreadMessageLike => ({
      id: m.id,
      role: m.role,
      content: textOf(m),
      // Keep the backend response so citations/status render after a reload.
      metadata: m.metadata.custom ? { custom: m.metadata.custom } : undefined,
    }),
  );
  const others = loadChats().filter((c) => c.id !== id);
  const chats = [{ id, title: titleOf(saved), updated: Date.now(), messages: saved }, ...others]
    .slice(0, MAX_SAVED_CHATS);
  save(CHATS_KEY, chats);
}

/** Start a new, empty chat; earlier ones stay in the list. */
export function startNewChat(): void {
  save(CURRENT_KEY, newId());
}

export function deleteChat(id: string): void {
  save(CHATS_KEY, loadChats().filter((c) => c.id !== id));
  if (load<string | null>(CURRENT_KEY, null) === id) startNewChat();
}
