import { UserRound } from "lucide-react";
import { emptyProfile, useProfile } from "../lib/profile";
import { citizenshipOptions } from "../lib/vocab";
import type { BuyerProfile } from "../lib/api";

const field =
  "mt-1 w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900";

/** Optional buyer details, sent with each question so answers can be specific. Replaces login. */
export function ProfilePanel() {
  const { profile, setProfile } = useProfile();
  const num = (v: string) => (v === "" ? null : Math.max(0, Number(v)));

  return (
    <section aria-labelledby="profile-heading" className="space-y-3">
      <h2 id="profile-heading" className="flex items-center gap-2 text-sm font-semibold">
        <UserRound size={16} /> Your situation
      </h2>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Optional. Helps the advisor give specific answers. Stays in this browser.
      </p>

      <label className="block text-xs font-medium">
        Household citizenship
        <select
          className={field}
          value={profile.citizenship ?? ""}
          onChange={(e) => setProfile({ ...profile, citizenship: e.target.value || null })}
        >
          <option value="">Not specified</option>
          {citizenshipOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label className="block text-xs font-medium">
        Household type
        <select
          className={field}
          value={profile.household_type ?? ""}
          onChange={(e) => setProfile({ ...profile, household_type: (e.target.value || null) as BuyerProfile["household_type"] })}
        >
          <option value="">Not specified</option>
          <option value="single">Single</option>
          <option value="couple_family">Couple / family</option>
          <option value="fiance">Fiancé / fiancée</option>
          <option value="extended_family">Extended family</option>
          <option value="senior">Senior household</option>
        </select>
      </label>

      <label className="block text-xs font-medium">
        Age (youngest buyer)
        <input
          type="number"
          min={0}
          max={120}
          inputMode="numeric"
          className={field}
          value={profile.age ?? ""}
          onChange={(e) => setProfile({ ...profile, age: num(e.target.value) })}
        />
      </label>

      <label className="block text-xs font-medium">
        Average gross monthly household income (SGD)
        <input
          type="number"
          min={0}
          step={100}
          inputMode="numeric"
          className={field}
          value={profile.household_income ?? ""}
          onChange={(e) => setProfile({ ...profile, household_income: num(e.target.value) })}
        />
      </label>

      <fieldset className="text-xs font-medium">
        <legend>Bought or received a housing subsidy before?</legend>
        <div className="mt-1 flex gap-3 font-normal">
          {[
            ["First-timer", true],
            ["Second-timer", false],
            ["Not sure", null],
          ].map(([label, value]) => (
            <label key={String(label)} className="flex items-center gap-1">
              <input
                type="radio"
                name="first_timer"
                checked={profile.first_timer === value}
                onChange={() => setProfile({ ...profile, first_timer: value as boolean | null })}
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <button
        onClick={() => setProfile(emptyProfile)}
        className="text-xs text-slate-500 underline hover:text-slate-700 dark:hover:text-slate-300"
      >
        Clear details
      </button>
    </section>
  );
}
