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

export type Route = "policy" | "price" | "mixed" | "discovery" | "clarify" | "abstain";

export type ChatStatus = "answered" | "clarifying" | "abstained";

export type ChatResponse = {
  status: ChatStatus;
  mode: string;
  route: Route | null;
  message: string;
  citations: PolicyPassage[];
  price_result: PriceResult | null;
  suggestions: Suggestion[];
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
