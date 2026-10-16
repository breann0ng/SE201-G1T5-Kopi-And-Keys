import { useOutletContext } from "react-router-dom";
import type { LayoutContext } from "../components/Layout";
import { useChat } from "../lib/chat";
import { usePrefs } from "../lib/prefs";
import { emptyProfile, useProfile } from "../lib/profile";
import { clearAll } from "../lib/storage";
import type { Theme } from "../lib/theme";

export function SettingsPage() {
  const { theme, setTheme } = useOutletContext<LayoutContext>();
  const { setProfile } = useProfile();
  const { newChat } = useChat();
  const { devDetails, setDevDetails } = usePrefs();

  const clearData = () => {
    if (!confirm("Clear your conversation, saved details, feedback and preferences from this browser?"))
      return;
    clearAll();
    newChat();
    setProfile(emptyProfile);
    setTheme("system");
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-8 px-4 py-8">
        <h1 className="text-2xl font-semibold">Settings</h1>

        <section>
          <h2 className="font-semibold">Appearance</h2>
          <div className="mt-2 flex gap-2">
            {(["system", "light", "dark"] as Theme[]).map((t) => (
              <button
                key={t}
                onClick={() => setTheme(t)}
                aria-pressed={theme === t}
                className={`rounded-lg border px-3 py-1.5 text-sm capitalize ${
                  theme === t
                    ? "border-brand-500 bg-brand-50 text-brand-700 dark:bg-slate-800 dark:text-brand-100"
                    : "border-slate-300 dark:border-slate-700"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2 className="font-semibold">Developer details</h2>
          <label className="mt-2 flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={devDetails}
              onChange={(e) => setDevDetails(e.target.checked)}
            />
            <span>
              Show how each answer was made: the graph steps the advisor took and the SQL query log.
              Useful for demos and debugging.
            </span>
          </label>
        </section>

        <section>
          <h2 className="font-semibold">Your data</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            There are no accounts. Your conversation, details, feedback and preferences are stored
            only in this browser. Your details (and, once conversation memory is switched on, your
            recent messages) are sent to our advisor service with each question and are not stored
            on the server.
          </p>
          <button
            onClick={clearData}
            className="mt-3 rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/40"
          >
            Clear my data
          </button>
        </section>

        <section className="text-sm text-slate-500">
          <h2 className="font-semibold text-slate-900 dark:text-slate-100">Coming later</h2>
          <ul className="mt-1 list-disc pl-5">
            <li>Multiple saved conversations</li>
            <li>Language options</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
