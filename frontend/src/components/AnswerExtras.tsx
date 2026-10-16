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

const sgd = (n: number | null) =>
  n === null ? "—" : n.toLocaleString("en-SG", { style: "currency", currency: "SGD", maximumFractionDigits: 0 });

function PriceCard({ price }: { price: PriceResult }) {
  const f = price.filters;
  return (
    <div className="mt-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
      <p className="text-xs text-slate-500">
        {f.flat_type} resale flats in {f.town}, {f.start_month} to {f.end_month} · {price.count}{" "}
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
              {sgd(value as number | null)}
            </div>
          </div>
        ))}
      </div>
    </div>
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
