import { Check, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

/**
 * Added 2026-10-17 (Sandra): real progress while an answer is being prepared.
 * Each line appears when the backend reports that graph step finished (POST /chat/stream);
 * nothing here is simulated. The model step is the slow one, so it carries the time hint.
 */
const DONE: Record<string, string> = {
  query_router: "Understood the question",
  policy_retrieval: "Found official passages",
  price_query: "Looked up resale prices",
  topic_cards: "Matched related topics",
  synthesiser: "Chose quotes from the official text",
  verifier: "Checked the quotes against their sources",
  cache: "Found this answer from earlier",
};

const node = (entry: string) => entry.split(":")[0];

function nextActivity(steps: string[]): string {
  const last = steps[steps.length - 1];
  if (last === "verifier:failed") return "A quote failed the check; asking for a corrected one…";
  switch (last && node(last)) {
    case undefined:
      return "Reading your question…";
    case "query_router":
      return "Searching official HDB and CPF pages…";
    case "policy_retrieval":
    case "price_query":
      return "Matching related topics…";
    case "topic_cards":
      return "Choosing quotes from the official text… this step usually takes under a minute";
    case "synthesiser":
      return "Checking every quote against its source…";
    case "verifier":
      return "Finishing up…";
    default:
      return "Finishing up…";
  }
}

export function Progress({ steps, started }: { steps: string[]; started: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const seconds = Math.max(0, Math.round((now - started) / 1000));
  const nodes = steps.map(node);
  const shown = nodes.filter((s, i) => DONE[s] && nodes.indexOf(s) === i);

  return (
    <div className="space-y-1.5 text-sm" aria-live="polite">
      {shown.map((s) => (
        <p key={s} className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
          <Check size={14} className="text-emerald-600" /> {DONE[s]}
        </p>
      ))}
      <p className="flex items-center gap-2 text-slate-700 dark:text-slate-200">
        <Loader2 size={14} className="animate-spin text-coral-500" />
        {nextActivity(steps)}
        <span className="ml-auto text-xs tabular-nums text-slate-400">{seconds} s</span>
      </p>
    </div>
  );
}
