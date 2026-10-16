import type { ThreadMessage, ThreadMessageLike } from "@assistant-ui/react";
import { load, save } from "./storage";

/**
 * Conversation memory, frontend half (option A in the team discussion).
 *
 * SEND_HISTORY is OFF until the backend's ChatRequest accepts a `history` field:
 * the backend rejects unknown fields (extra="forbid"), so sending it early would
 * fail every request. Turn on with VITE_SEND_HISTORY=true in frontend/.env.local.
 */
export const SEND_HISTORY = import.meta.env.VITE_SEND_HISTORY === "true";

/** Previous turns sent to the model. Kept small for the local model's context window. */
export const MAX_HISTORY_MESSAGES = 6;

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
    .map((m) => ({ role: m.role as "user" | "assistant", content: textOf(m) }))
    .filter((t) => t.content)
    .slice(-MAX_HISTORY_MESSAGES);
}

// ---- Saving the visible conversation in this browser (survives reloads) ----

const KEY = "kk:chat";
const MAX_SAVED_MESSAGES = 60;

export function loadChat(): ThreadMessageLike[] {
  return load<ThreadMessageLike[]>(KEY, []);
}

export function saveChat(messages: readonly ThreadMessage[]): void {
  const done = messages.filter((m) => m.status?.type !== "running");
  save(
    KEY,
    done.slice(-MAX_SAVED_MESSAGES).map(
      (m): ThreadMessageLike => ({
        id: m.id,
        role: m.role,
        content: textOf(m),
        // Keep the backend response so citations/status render after a reload.
        metadata: m.metadata.custom ? { custom: m.metadata.custom } : undefined,
      }),
    ),
  );
}

export function clearChat(): void {
  save(KEY, []);
}
