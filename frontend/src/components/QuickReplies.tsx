import type { BuyerProfile } from "../lib/api";
import { useChat } from "../lib/chat";
import { useProfile } from "../lib/profile";
import { citizenshipOptions } from "../lib/vocab";

type Option = { label: string; value: BuyerProfile[keyof BuyerProfile] };

/** Clarification fields with buttons: profile fields, plus price filters that are not profile fields. */
export type QuickReplyField = keyof BuyerProfile | "flat_type";

// Price filters: the button only sends the answer as a chat message (the backend resumes the
// price question from it); there is no sidebar profile field to fill in.
const MESSAGE_ONLY: Partial<Record<QuickReplyField, string[]>> = {
  flat_type: ["2-room", "3-room", "4-room", "5-room", "Executive"],
};

// Fields answered with a button. age / household_income are typed in the chat box.
const OPTIONS: Partial<Record<keyof BuyerProfile, Option[]>> = {
  citizenship: citizenshipOptions.map((o) => ({ label: o.label, value: o.value })),
  first_timer: [
    { label: "First-timer (never bought or received a housing subsidy)", value: true },
    { label: "Second-timer", value: false },
  ],
  household_type: [
    { label: "I am buying as a single", value: "single" },
    { label: "We are a couple / family", value: "couple_family" },
  ],
};

/**
 * Buttons under a clarifying question. Tapping one fills in the sidebar profile and sends
 * the answer as a chat message, so it works with or without conversation memory.
 * The backend's `asking_for` field selects the relevant options.
 */
export function QuickReplies({ field }: { field: QuickReplyField }) {
  const { runtime } = useChat();
  const { profile, setProfile } = useProfile();
  const messages = MESSAGE_ONLY[field];
  if (messages) {
    return (
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Quick replies">
        {messages.map((label) => (
          <button
            key={label}
            onClick={() => runtime.thread.append(label)}
            className="rounded-full border border-coral-300 bg-white px-3 py-1 text-sm hover:bg-coral-50 dark:border-coral-500/60 dark:bg-slate-900 dark:hover:bg-slate-800"
          >
            {label}
          </button>
        ))}
      </div>
    );
  }
  const options = OPTIONS[field as keyof BuyerProfile];
  if (!options) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Quick replies">
      {options.map((o) => (
        <button
          key={String(o.value)}
          onClick={() => {
            setProfile({ ...profile, [field as keyof BuyerProfile]: o.value });
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
