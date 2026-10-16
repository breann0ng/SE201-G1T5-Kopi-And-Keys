import type { ChatModelAdapter } from "@assistant-ui/react";
import { ApiError, postChat, type BuyerProfile, type ChatResponse } from "./api";
import { SEND_HISTORY, toHistory } from "./history";

/** What the assistant message carries in metadata.custom, read by AssistantMessage. */
export type AdvisorMeta =
  | { kind: "response"; response: ChatResponse }
  | { kind: "error"; error: string };

/** Display only: turn "[source-id]" markers into "[1]", "[2]" matching the Sources list. */
function numberCitations(response: ChatResponse): string {
  let text = response.message;
  response.citations.forEach((c, i) => {
    text = text.split(`[${c.id}]`).join(`[${i + 1}]`);
  });
  return text;
}

/**
 * Bridges assistant-ui to POST /chat with the latest message and current profile.
 * The backend is stateless; recent turns are added as `history` once SEND_HISTORY is on.
 */
export function createAdvisorAdapter(getProfile: () => BuyerProfile): ChatModelAdapter {
  return {
    async run({ messages, abortSignal }) {
      const last = messages[messages.length - 1];
      const text = last.content
        .map((part) => (part.type === "text" ? part.text : ""))
        .join("\n")
        .trim();
      try {
        const history = SEND_HISTORY ? toHistory(messages.slice(0, -1)) : null;
        const response = await postChat(text, getProfile(), history, abortSignal);
        return {
          content: [{ type: "text", text: numberCitations(response) }],
          metadata: { custom: { kind: "response", response } satisfies AdvisorMeta },
        };
      } catch (err) {
        if ((err as Error).name === "AbortError") throw err;
        const error = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
        return {
          content: [{ type: "text", text: error }],
          metadata: { custom: { kind: "error", error } satisfies AdvisorMeta },
        };
      }
    },
  };
}
