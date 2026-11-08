import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import activeRaw from "../../../data/policy_snapshots/ACTIVE?raw";

// Read straight from the committed snapshot so this page always matches ACTIVE.
// TODO(backend): serve this from an API endpoint once the retriever loads snapshots.
type Page = {
  slug: string;
  final_url: string | null;
  page_title: string | null;
  source_tier: number | null;
  last_updated_printed: string | null;
};
type Manifest = { snapshot_date: string; pages: Page[] };

const manifests = import.meta.glob<Manifest>("../../../data/policy_snapshots/*/manifest.json", {
  import: "default",
});
const active = activeRaw.trim();
// Snapshots captured after ACTIVE are candidates still waiting for review (data/README.md, 4.1).
const pending = Object.keys(manifests)
  .map((path) => path.split("/").slice(-2, -1)[0] ?? "")
  .filter((date) => date > active)
  .sort();

const TIERS: Record<number, string> = {
  1: "Official scheme pages (HDB, CPF) and HDB documents",
  2: "HDB MyNiceHome guides",
  3: "CPF explainer articles",
};

export function SourcesPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const load = manifests[`../../../data/policy_snapshots/${active}/manifest.json`];
    if (!load) {
      setError(true);
      return;
    }
    load().then(setManifest, () => setError(true));
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
        <header>
          <h1 className="text-2xl font-semibold">Sources &amp; methodology</h1>
          <p className="mt-2 text-slate-600 dark:text-slate-400">
            Answers are based only on official pages from hdb.gov.sg, cpf.gov.sg and
            mynicehome.gov.sg, captured on{" "}
            <strong className="text-slate-900 dark:text-slate-100">{active}</strong>. The advisor
            cites the page and the date it was checked. If a page doesn't cover your situation, the
            advisor says so rather than guessing.
          </p>
        </header>

        <section className="rounded-xl border border-slate-200 p-4 text-sm dark:border-slate-800">
          <h2 className="font-semibold">How we keep it current</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600 dark:text-slate-400">
            <li>
              A monthly check, and a manual one after announced policy changes, captures these pages
              again when the official sites allow it.
            </li>
            <li>
              A new capture is used only after a person reviews every change in figures. Until then,
              answers stay on the capture above.
            </li>
            {pending.length > 0 && (
              <li>
                A newer capture from <strong>{pending[pending.length - 1]}</strong> is waiting for review.
              </li>
            )}
            <li>Outdated passages are marked superseded and can no longer be cited.</li>
            <li>We only show an "effective date" when the official page states one.</li>
          </ul>
        </section>

        {error && <p className="text-red-600">Couldn't load the source list for {active}.</p>}
        {!manifest && !error && <p className="text-slate-500">Loading sources…</p>}

        {manifest &&
          [1, 2, 3].map((tier) => {
            const pages = manifest.pages.filter((p) => p.source_tier === tier && p.final_url);
            if (!pages.length) return null;
            return (
              <section key={tier}>
                <h2 className="font-semibold">
                  {TIERS[tier]} <span className="font-normal text-slate-500">({pages.length})</span>
                </h2>
                <ul className="mt-2 divide-y divide-slate-200 rounded-xl border border-slate-200 text-sm dark:divide-slate-800 dark:border-slate-800">
                  {pages.map((p) => (
                    <li key={p.slug} className="flex items-start justify-between gap-3 px-3 py-2">
                      <a
                        href={p.final_url!}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-brand-600 hover:underline dark:text-brand-100"
                      >
                        {p.page_title ?? p.slug} <ExternalLink size={12} className="shrink-0" />
                      </a>
                      {p.last_updated_printed && (
                        <span className="shrink-0 text-xs text-slate-500">
                          {p.last_updated_printed}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
      </div>
    </div>
  );
}
