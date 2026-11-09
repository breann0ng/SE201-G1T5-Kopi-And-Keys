import type { ChatResponse } from "./api";

/** Fixed backend outcomes, not text inferred from a model's answer. */
export function abstentionHeading(response: Pick<ChatResponse, "trace">): string {
  if (response.trace.includes("abstention:no_transactions")) return "No matching resale transactions";
  if (response.trace.includes("abstention:price_out_of_range")) return "No resale data for that period";
  if (response.trace.includes("abstention:profile_scope")) return "I can't assess this profile from these conditions";
  return "I can't answer this reliably from official sources";
}
