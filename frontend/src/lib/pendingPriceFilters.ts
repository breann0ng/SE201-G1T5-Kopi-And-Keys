import type { PriceFilters } from "./api";

/**
 * Structured price filters from the "Narrow it down" form, sent with the next chat message
 * as `price_filters` (exact values, so the backend never has to parse them from text).
 * The form sets them just before appending its message; the adapter takes them once.
 */
let pending: PriceFilters | null = null;

export function setPendingPriceFilters(filters: PriceFilters): void {
  pending = filters;
}

export function takePendingPriceFilters(): PriceFilters | null {
  const filters = pending;
  pending = null;
  return filters;
}
