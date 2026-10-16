// Mirrors backend/kopi_keys/schemas.py. Keep in sync when the contract changes.
import type { HistoryTurn } from "./history";

export type BuyerProfile = {
  citizenship: string | null;
  age: number | null;
  household_income: number | null;
  first_timer: boolean | null;
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
  count: number;
  median: number | null;
  minimum: number | null;
  maximum: number | null;
};

export type ChatStatus = "answered" | "clarifying" | "abstained";

export type ChatResponse = {
  status: ChatStatus;
  mode: string;
  message: string;
  citations: PolicyPassage[];
  price_result: PriceResult | null;
  retrieval_rounds: number;
  trace: string[];
  /**
   * PROPOSED (not in the backend yet): on a "clarifying" reply, the profile field being
   * asked about, e.g. "citizenship". Lets the UI offer quick-reply buttons.
   */
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
      // `history` is only sent when enabled; the current backend rejects unknown fields.
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
