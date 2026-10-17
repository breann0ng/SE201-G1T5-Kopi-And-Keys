// Mirrors backend/kopi_keys/schemas.py. Keep in sync when the contract changes.
import type { HistoryTurn } from "./history";

export type BuyerProfile = {
  citizenship: string | null;
  age: number | null;
  household_income: number | null;
  first_timer: boolean | null;
  household_type: "single" | "couple_family" | "fiance" | "extended_family" | "senior" | null;
};

export type PolicyPassage = {
  id: string;
  title: string;
  text: string;
  source_url: string;
  effective_date: string | null;
  verified_on: string;
  page_last_updated: string | null;
  snapshot_id: string;
  superseded: boolean;
};

export type PriceResult = {
  query_id: string;
  filters: { town: string; flat_type: string; start_month: string; end_month: string };
  volume: number;
  // Decimals: the backend serialises these as strings (e.g. "512000.00").
  mean: string | null;
  median: string | null;
  iqr: string | null;
  minimum: string | null;
  maximum: string | null;
};

export type Suggestion = {
  card_id: string;
  text: string;
  citation_ids: string[];
};

/** A broad question's overview row: an official sentence quoted verbatim, with its source. */
export type OverviewItem = {
  card_id: string;
  title: string;
  quote: string;
  citation_id: string;
};

/** A grant's income ceiling compared with the stated income. Never an eligibility verdict. */
export type IncomeNote = {
  scheme: string;
  label: string;
  ceiling: string;
  within_ceiling: boolean;
  message: string;
  source_url: string;
  /** HDB's ceiling variants, verbatim (e.g. a higher ceiling for extended families). */
  conditions?: string[];
};

export type Route = "policy" | "price" | "mixed" | "discovery" | "clarify" | "abstain";

export type ChatStatus = "answered" | "clarifying" | "abstained";

export type ChatResponse = {
  status: ChatStatus;
  /** Policy evidence source: "demo" = fictional test passages (UI warns), "snapshot" = official ACTIVE snapshot. */
  mode: "demo" | "snapshot";
  route: Route | null;
  message: string;
  citations: PolicyPassage[];
  price_result: PriceResult | null;
  suggestions: Suggestion[];
  /** Broad questions only (e.g. "What grants are there?"); absent in older saved chats. */
  overview?: OverviewItem[];
  /** Retrieved passages the answer did not quote; absent in older saved chats. */
  related?: PolicyPassage[];
  /** Grant questions with a stated income; absent in older saved chats. */
  income_notes?: IncomeNote[];
  /** Discovery question where filling in "Your situation" would unlock tailored suggestions. */
  profile_hint?: boolean;
  retrieval_rounds: number;
  trace: string[];
  /** Profile field requested by a clarification; drives quick-reply buttons. */
  asking_for?: keyof BuyerProfile | null;
};

export class ApiError extends Error {}

export async function postChat(
  message: string,
  profile: BuyerProfile,
  history: HistoryTurn[] | null,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  let res: Response;
  try {
    res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Recent turns are conversation context, not policy evidence.
      body: JSON.stringify(history ? { message, profile, history } : { message, profile }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Can't reach the advisor service. Is the backend running?");
  }
  if (!res.ok) {
    throw new ApiError(`The advisor service returned an error (HTTP ${res.status}).`);
  }
  return (await res.json()) as ChatResponse;
}

/** One line of POST /chat/stream: a finished graph step, or the final answer. */
export type StreamEvent = { step: string; trace?: string[] } | { response: ChatResponse };

/**
 * Added 2026-10-17 (Sandra): the same answer as postChat, plus each graph step as it finishes,
 * so the UI can show real progress during the ~40-60 s model step. Falls back to /chat on an
 * older backend without the stream endpoint.
 */
export async function* streamChat(
  message: string,
  profile: BuyerProfile,
  history: HistoryTurn[] | null,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  let res: Response;
  try {
    res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(history ? { message, profile, history } : { message, profile }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Can't reach the advisor service. Is the backend running?");
  }
  if (res.status === 404 || !res.body) {
    yield { response: await postChat(message, profile, history, signal) };
    return;
  }
  if (!res.ok) throw new ApiError(`The advisor service returned an error (HTTP ${res.status}).`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) if (line.trim()) yield JSON.parse(line) as StreamEvent;
    if (done) break;
  }
  if (buffer.trim()) yield JSON.parse(buffer) as StreamEvent;
}
