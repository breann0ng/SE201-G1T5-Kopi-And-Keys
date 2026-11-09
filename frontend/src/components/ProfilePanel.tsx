import { UserRound } from "lucide-react";
import { useChat } from "../lib/chat";
import { emptyProfile, useProfile } from "../lib/profile";
import { clearAll } from "../lib/storage";
import { citizenshipOptions } from "../lib/vocab";
import type { BuyerProfile } from "../lib/api";
import { profileWarnings } from "../lib/profileWarnings";

const field =
  "mt-1 w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900";

/** Optional buyer details, sent with each question so answers can be specific. Replaces login. */
export function ProfilePanel() {
  const { profile, setProfile } = useProfile();
  const { newChat } = useChat();
  const warnings = profileWarnings(profile);
  const num = (v: string) => (v === "" ? null : Math.max(0, Number(v)));

  return (
    <section aria-labelledby="profile-heading" className="space-y-3">
      <h2 id="profile-heading" className="flex items-center gap-2 text-sm font-semibold">
        <UserRound size={16} /> Your situation
      </h2>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Optional. Applied to your next question. Earlier answers keep their original context.
      </p>
      {warnings.length > 0 && (
        <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
          <p className="font-semibold">Check your profile details</p>
          <ul className="mt-1 list-disc space-y-1 pl-4">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          <p className="mt-1">Correct these selections before asking for policy guidance. Transaction prices can still be checked.</p>
        </div>
      )}

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
        <legend>Subsidy history of the buying household</legend>
        <div className="mt-1 flex flex-col gap-2 font-normal">
          {[
            ["First-timer household", "first_timer"],
            ["Second-timer household", "second_timer"],
            ["Mixed first-/second-timer couple", "mixed"],
            ["Not sure", null],
          ].map(([label, value]) => (
            <label key={String(label)} className="flex items-center gap-1">
              <input
                type="radio"
                name="first_timer"
                checked={profile.subsidy_status === value}
                onChange={() => setProfile({ ...profile,
                  subsidy_status: value as BuyerProfile["subsidy_status"],
                  first_timer: value === null ? null : value === "first_timer" })}
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

      <div className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-800">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          No accounts: chats and details stay in this browser. Questions go to the advisor and its
          model service. Ratings you send are kept for the team to review and never change answers.
        </p>
        <button
          onClick={() => {
            if (!confirm("Clear your conversations, saved details and preferences from this browser?")) return;
            clearAll();
            newChat();
            setProfile(emptyProfile);
          }}
          className="rounded-lg border border-red-300 px-3 py-1.5 text-xs text-red-700 hover:bg-red-50"
        >
          Clear my data
        </button>
      </div>
    </section>
  );
}
