import type { BuyerProfile } from "./api";

/** Structural conflicts between selectors; never an eligibility/age/income verdict. */
export function profileWarnings(profile: BuyerProfile): string[] {
  const warnings: string[] = [];
  if (profile.citizenship === "SC_single" && ["couple_family", "fiance", "extended_family"].includes(profile.household_type ?? "")) {
    warnings.push("Single Singapore Citizen conflicts with a family household. Check Household citizenship or Household type.");
  }
  if (profile.household_type === "single" && ["SC/SC", "SC/SPR", "SPR/SPR"].includes(profile.citizenship ?? "")) {
    warnings.push("A two-person citizenship household conflicts with Single. Check Household citizenship or Household type.");
  }
  if (profile.subsidy_status === "mixed" && (profile.household_type === "single" || profile.citizenship === "SC_single")) {
    warnings.push("Mixed first-/second-timer couple conflicts with a single-person household. Check the household and subsidy selections.");
  }
  return warnings;
}
