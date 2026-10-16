import { AlertTriangle, ExternalLink, HelpCircle, ShieldCheck } from "lucide-react";
import type { AdvisorMeta } from "../lib/adapter";
import type { ChatResponse, PolicyPassage, PriceResult } from "../lib/api";
import { usePrefs } from "../lib/prefs";
import { AnswerTrace } from "./AnswerTrace";

export function StatusBadge({ meta }: { meta: AdvisorMeta | undefined }) {
  if (!meta) return null;
  if (meta.kind === "error") {
    return (
      <Badge className="text-red-700 dark:text-red-300">
        <AlertTriangle size={14} /> Couldn't get an answer
      </Badge>
    );
  }
  if (meta.response.status === "clarifying") {
    return (
      <Badge className="text-amber-700 dark:text-amber-300">
        <HelpCircle size={14} /> I need a bit more information
      </Badge>
    );
  }
  if (meta.response.status === "abstained") {
    return (
      <Badge className="text-slate-600 dark:text-slate-300">
        <AlertTriangle size={14} /> I can't answer this reliably from official sources
      </Badge>
    );
  }
  return null;
}

function Badge({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <div className={`mb-2 flex items-center gap-1.5 text-xs font-medium ${className}`}>{children}</div>
  );
}

export function AnswerExtras({ response }: { response: ChatResponse }) {
  const { devDetails } = usePrefs();
  return (
    <>
      {response.price_result && <PriceCard price={response.price_result} />}
      {response.citations.length > 0 && <Citations citations={response.citations} />}
      {response.status === "abstained" && (
        <p className="mt-3 text-sm">
          Please check{" "}
          <a
            className="text-brand-600 underline dark:text-brand-100"
            href="https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility"
            target="_blank"
            rel="noreferrer"
          >
            HDB's eligibility pages
          </a>{" "}
          or contact HDB directly.
        </p>
      )}
      {devDetails && <AnswerTrace response={response} />}
      {response.mode === "demo" && (
        <p className="mt-3 text-xs text-slate-400">
          Demo mode: the backend is using fictional sample evidence.
        </p>
      )}
    </>
  );
}

const sgd = (n: string | null) =>
  n === null ? "—" : Number(n).toLocaleString("en-SG", { style: "currency", currency: "SGD", maximumFractionDigits: 0 });

function PriceCard({ price }: { price: PriceResult }) {
  const f = price.filters;
  return (
    <div className="mt-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
      <p className="text-xs text-slate-500">
        {f.flat_type} resale flats in {f.town}, {f.start_month} to {f.end_month} · {price.volume}{" "}
        transactions
      </p>
      <div className="mt-2 grid grid-cols-3 gap-2 text-center">
        {[
          ["Lowest", price.minimum],
          ["Median", price.median],
          ["Highest", price.maximum],
        ].map(([label, value]) => (
          <div key={label as string}>
            <div className="text-xs text-slate-500">{label}</div>
            <div className={`font-semibold ${label === "Median" ? "text-lg" : ""}`}>
              {sgd(value as string | null)}
            </div>
          </div>
        ))}
      </div>
      <PriceRange price={price} />
      {price.volume > 0 && price.volume < 10 && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
          Only {price.volume} sales: treat these figures with caution.
        </p>
      )}
    </div>
  );
}

/** Range bar: lowest to highest sale, with the median (dot) and mean (tick) placed to scale. */
function PriceRange({ price }: { price: PriceResult }) {
  const [lo, hi, med, mean] = [price.minimum, price.maximum, price.median, price.mean].map((v) =>
    v === null ? null : Number(v),
  );
  if (lo === null || hi === null || med === null || hi <= lo) return null;
  const pos = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  return (
    <figure className="mt-3" aria-label="Price range from lowest to highest sale">
      <div className="relative mx-2 h-6">
        <div className="absolute top-1/2 h-1.5 w-full -translate-y-1/2 rounded-full bg-gradient-to-r from-slate-200 via-coral-300 to-slate-200 dark:from-slate-700 dark:via-coral-500/40 dark:to-slate-700" />
        {mean !== null && (
          <div
            className="absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-slate-500"
            style={{ left: pos(mean) }}
            title={`Mean ${sgd(price.mean)}`}
          />
        )}
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-coral-500 shadow dark:border-slate-900"
          style={{ left: pos(med) }}
          title={`Median ${sgd(price.median)}`}
        />
      </div>
      <figcaption className="mt-1 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-coral-500" /> Median
        </span>
        {mean !== null && (
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-0.5 bg-slate-500" /> Mean {sgd(price.mean)}
          </span>
        )}
        {price.iqr !== null && <span>Middle 50% of sales span {sgd(price.iqr)}</span>}
      </figcaption>
    </figure>
  );
}

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-SG", { day: "numeric", month: "short", year: "numeric" });

function Citations({ citations }: { citations: PolicyPassage[] }) {
  return (
    <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-500">
        <ShieldCheck size={14} className="text-coral-500" /> Sources
      </p>
      <ol className="space-y-2">
        {citations.map((c, i) => (
          <li key={c.id} className="text-sm">
            <a
              href={c.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium text-brand-600 hover:underline dark:text-brand-100"
            >
              [{i + 1}] {c.title} <ExternalLink size={12} />
            </a>
            <div className="text-xs text-slate-500">
              Verified on official site {fmtDate(c.verified_on)}
              {c.page_last_updated && ` · page says "${c.page_last_updated}"`}
              {c.effective_date && ` · effective ${fmtDate(c.effective_date)}`}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
