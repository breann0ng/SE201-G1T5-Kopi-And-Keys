import type { BuyerProfile } from "../lib/api";
import { useChat } from "../lib/chat";
import { useProfile } from "../lib/profile";
import { citizenshipOptions } from "../lib/vocab";

type Option = { label: string; value: BuyerProfile[keyof BuyerProfile] };

// Fields answered with a button. age / household_income are typed in the chat box.
const OPTIONS: Partial<Record<keyof BuyerProfile, Option[]>> = {
  citizenship: citizenshipOptions.map((o) => ({ label: o.label, value: o.value })),
  first_timer: [
    { label: "First-timer (never bought or received a housing subsidy)", value: true },
    { label: "Second-timer", value: false },
  ],
};

/**
 * Buttons under a clarifying question. Tapping one fills in the sidebar profile and sends
 * the answer as a chat message, so it works with or without conversation memory.
 * Needs the backend's proposed `asking_for` field; shows nothing until that exists.
 */
export function QuickReplies({ field }: { field: keyof BuyerProfile }) {
  const { runtime } = useChat();
  const { profile, setProfile } = useProfile();
  const options = OPTIONS[field];
  if (!options) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Quick replies">
      {options.map((o) => (
        <button
          key={String(o.value)}
          onClick={() => {
            setProfile({ ...profile, [field]: o.value });
            runtime.thread.append(o.label);
          }}
          className="rounded-full border border-coral-300 bg-white px-3 py-1 text-sm hover:bg-coral-50 dark:border-coral-500/60 dark:bg-slate-900 dark:hover:bg-slate-800"
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
