import type { LeaseBand, PriceFilters, StoreyBand } from "./api";

// Bands match backend/kopi_keys/components/price_query.py (LEASE_BANDS, STOREY_BANDS).
export const LEASE: { value: LeaseBand; label: string }[] = [
  { value: "under_60", label: "Under 60 yrs" },
  { value: "60_79", label: "60–79 yrs" },
  { value: "80_plus", label: "80+ yrs" },
];
export const STOREY: { value: StoreyBand; label: string }[] = [
  { value: "low", label: "Low (1–6)" },
  { value: "mid", label: "Mid (7–12)" },
  { value: "high", label: "High (13+)" },
];
/** Short labels for a refined card's header and table captions. */
export function bandLabels(filters: PriceFilters): { lease?: string; storey?: string } {
  return {
    lease: filters.lease_band ? `${LEASE.find((l) => l.value === filters.lease_band)?.label} lease left` : undefined,
    storey: filters.storey_band
      ? `${STOREY.find((s) => s.value === filters.storey_band)?.label.replace(/ \(.*/, "").toLowerCase()} floors`
      : undefined,
  };
}

