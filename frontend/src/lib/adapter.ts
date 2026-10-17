import type { ChatModelAdapter } from "@assistant-ui/react";
import { ApiError, streamChat, type BuyerProfile, type ChatResponse } from "./api";
import { SEND_HISTORY, toHistory } from "./history";

/** What the assistant message carries in metadata.custom, read by AssistantMessage. */
export type AdvisorMeta =
  | { kind: "response"; response: ChatResponse }
  | { kind: "error"; error: string };

/** While running: graph steps finished so far as trace entries ("verifier:failed"), from
 * /chat/stream, and when the request began. Replaced by AdvisorMeta when the answer arrives. */
export type ProgressMeta = { kind: "progress"; steps: string[]; started: number };

/** Display only: turn "[source-id]" markers into "[1]", "[2]" matching the Sources list. */
function numberCitations(response: ChatResponse): string {
  let text = response.message;
  response.citations.forEach((c, i) => {
    text = text.split(`[${c.id}]`).join(`[${i + 1}]`);
  });
  return text;
}

/**
 * Bridges assistant-ui to POST /chat/stream with the latest message and current profile,
 * yielding progress (finished graph steps) until the answer arrives.
 * The backend is stateless; recent turns are added as `history` once SEND_HISTORY is on.
 */
export function createAdvisorAdapter(getProfile: () => BuyerProfile): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const last = messages[messages.length - 1];
      const text = last.content
        .map((part) => (part.type === "text" ? part.text : ""))
        .join("\n")
        .trim();
      try {
        const history = SEND_HISTORY ? toHistory(messages.slice(0, -1)) : null;
        const started = Date.now();
        const steps: string[] = [];
        let response: ChatResponse | null = null;
        yield { metadata: { custom: { kind: "progress", steps: [], started } satisfies ProgressMeta } };
        for await (const event of streamChat(text, getProfile(), history, abortSignal)) {
          if ("step" in event) {
            steps.push(event.trace?.[0] ?? event.step);
            yield { metadata: { custom: { kind: "progress", steps: [...steps], started } satisfies ProgressMeta } };
          } else {
            response = event.response;
          }
        }
        if (!response) throw new ApiError("The advisor service ended without an answer. Please try again.");
        yield {
          content: [{ type: "text", text: numberCitations(response) }],
          metadata: { custom: { kind: "response", response } satisfies AdvisorMeta },
        };
      } catch (err) {
        if ((err as Error).name === "AbortError") throw err;
        const error = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
        yield {
          content: [{ type: "text", text: error }],
          metadata: { custom: { kind: "error", error } satisfies AdvisorMeta },
        };
      }
    },
  };
}
