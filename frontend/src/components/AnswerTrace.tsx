import { Database, ListTree } from "lucide-react";
import type { ChatResponse } from "../lib/api";

/** Human-readable label for one workflow trace step (backend/kopi_keys/workflow.py). */
function describe(step: string): string {
  const [kind, detail = ""] = step.split(":", 2);
  switch (kind) {
    case "advisor":
      return `Advisor decided: ${detail}`;
    case "retrieval":
      return `Policy search returned ${detail}`;
    case "price":
      return detail === "result" ? "SQL price query returned a result" : `SQL price query: ${detail}`;
    case "verifier":
      return detail === "passed" ? "Verifier passed the answer" : "Verifier rejected the draft";
    default:
      return step;
  }
}

/**
 * Developer details under an answer: the graph steps taken and the SQL query log.
 * Shown only when Settings → "Show developer details" is on (for demos and debugging).
 */
export function AnswerTrace({ response }: { response: ChatResponse }) {
  const price = response.price_result;
  return (
    <details className="mt-3 rounded-lg border border-slate-200 text-xs dark:border-slate-700">
      <summary className="cursor-pointer px-3 py-2 font-medium text-slate-600 dark:text-slate-300">
        How this answer was made
      </summary>
      <div className="space-y-3 px-3 pb-3">
        <section>
          <h4 className="mb-1 flex items-center gap-1.5 font-medium">
            <ListTree size={13} /> Graph steps ({response.trace.length})
          </h4>
          {response.trace.length ? (
            <ol className="list-decimal space-y-0.5 pl-5 font-mono text-[11px] text-slate-600 dark:text-slate-400">
              {response.trace.map((step, i) => (
                <li key={i} title={step}>
                  {describe(step)}
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-slate-500">No steps recorded.</p>
          )}
          <p className="mt-1 text-slate-500">
            Retrieval rounds: {response.retrieval_rounds} · Status: {response.status} · Mode: {response.mode}
          </p>
        </section>
        <section>
          <h4 className="mb-1 flex items-center gap-1.5 font-medium">
            <Database size={13} /> SQL execution log
          </h4>
          {price ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px] text-slate-600 dark:text-slate-400">
              <dt>query_id</dt>
              <dd>{price.query_id}</dd>
              <dt>filters</dt>
              <dd>
                town={price.filters.town}, flat_type={price.filters.flat_type}, {price.filters.start_month} to{" "}
                {price.filters.end_month}
              </dd>
              <dt>rows</dt>
              <dd>{price.volume}</dd>
            </dl>
          ) : (
            <p className="text-slate-500">No SQL query ran for this answer.</p>
          )}
        </section>
      </div>
    </details>
  );
}
