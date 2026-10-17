import { useState } from "react";
import type { BandStat, LeaseBand, PriceFilters, PriceResult, StoreyBand } from "../lib/api";
import { LEASE, MIN_SUMMARY_VOLUME, STOREY, bandLabels } from "../lib/priceBands";
import { useChat } from "../lib/chat";
import { setPendingPriceFilters } from "../lib/pendingPriceFilters";

const PERIODS = [
  { months: 0, label: "Same period" },
  { months: 12, label: "Last 12 months" },
  { months: 6, label: "Last 6 months" },
  { months: 3, label: "Last 3 months" },
];

const sgd0 = (n: string | null) =>
  n === null ? "—" : Number(n).toLocaleString("en-SG", { style: "currency", currency: "SGD", maximumFractionDigits: 0 });

function stat(breakdown: BandStat[], dimension: "lease" | "storey", band: string) {
  return breakdown.find((b) => b.dimension === dimension && b.band === band);
}

/** Median by remaining lease and by floor, so a single overall median is never read on its own. */
export function BandTables({ price }: { price: PriceResult }) {
  const breakdown = price.breakdown ?? [];
  if (!breakdown.length) return null;
  const table = (title: string, dimension: "lease" | "storey", rows: { value: string; label: string }[], current?: string | null) => (
    <table className="w-full text-xs">
      <caption className="mb-1 text-left font-medium text-slate-600 dark:text-slate-300">{title}</caption>
      <thead>
        <tr className="text-slate-500">
          <th className="text-left font-normal">Band</th>
          <th className="text-right font-normal">Sales</th>
          <th className="text-right font-normal">Median</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const s = stat(breakdown, dimension, r.value);
          if (!s || s.volume === 0) return null;
          return (
            <tr key={r.value} className={current === r.value ? "font-semibold" : ""}>
              <td className="py-0.5">{r.label}</td>
              <td className="py-0.5 text-right">{s.volume}</td>
              <td className="py-0.5 text-right" title={s.volume < MIN_SUMMARY_VOLUME ? "Too few sales for a median" : undefined}>
                {s.volume < MIN_SUMMARY_VOLUME ? "—" : sgd0(s.median)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
  // Each table is computed with the other refinement applied; say so in its caption.
  const labels = bandLabels(price.filters);
  return (
    <div className="mt-3 grid gap-4 border-t border-slate-200 pt-3 sm:grid-cols-2 dark:border-slate-700">
      {table(`By remaining lease${labels.storey ? ` (${labels.storey})` : ""}`, "lease", LEASE, price.filters.lease_band)}
      {table(`By floor${labels.lease ? ` (${labels.lease})` : ""}`, "storey", STOREY, price.filters.storey_band)}
      {breakdown.some((b) => b.volume > 0 && b.volume < MIN_SUMMARY_VOLUME) && (
        <p className="text-xs text-slate-500 sm:col-span-2">— fewer than {MIN_SUMMARY_VOLUME} sales: too few for a median.</p>
      )}
    </div>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthLabel = (yyyyMm: string) => {
  const [y, m] = yyyyMm.split("-");
  return `${MONTHS[Number(m) - 1]} ${y}`;
};

/** The latest matching sales: real comparables, not a valuation. */
export function RecentSales({ price, open = false }: { price: PriceResult; open?: boolean }) {
  const sales = price.recent_sales ?? [];
  if (!sales.length) return null;
  const all = sales.length === price.volume;
  return (
    <details open={open} className="mt-3 border-t border-slate-200 pt-2 text-xs dark:border-slate-700">
      <summary className="cursor-pointer font-medium text-slate-600 dark:text-slate-300">
        {all ? `All ${sales.length} matching ${sales.length === 1 ? "sale" : "sales"}` : `${sales.length} most recent matching sales`}
      </summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[480px]">
          <thead>
            <tr className="text-slate-500">
              <th className="text-left font-normal">Month</th>
              <th className="text-left font-normal">Block</th>
              <th className="text-left font-normal">Floor</th>
              <th className="text-right font-normal">Size</th>
              <th className="text-left font-normal pl-2">Lease left</th>
              <th className="text-right font-normal">Price</th>
            </tr>
          </thead>
          <tbody>
            {sales.map((s, i) => (
              <tr key={i}>
                <td className="py-0.5">{monthLabel(s.month)}</td>
                <td className="py-0.5">
                  {s.block} {s.street_name.toLowerCase().replace(/[a-z]+/g, (w) => w[0].toUpperCase() + w.slice(1))}
                </td>
                <td className="py-0.5">{s.storey_range.replace(" TO ", "–")}</td>
                <td className="py-0.5 text-right">{Number(s.floor_area_sqm)} m²</td>
                <td className="py-0.5 pl-2">{s.remaining_lease}</td>
                <td className="py-0.5 text-right">{sgd0(s.resale_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function shiftMonth(yyyyMm: string, delta: number): string {
  const [y, m] = yyyyMm.split("-").map(Number);
  const index = y * 12 + (m - 1) + delta;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

function Chip({ active, disabled, onClick, children }: {
  active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-pressed={active}
      className={
        "rounded-full border px-2.5 py-0.5 text-xs disabled:cursor-not-allowed disabled:opacity-40 " +
        (active
          ? "border-coral-500 bg-coral-50 text-coral-600 dark:bg-coral-500/20 dark:text-coral-300"
          : "border-slate-300 bg-white hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:hover:bg-slate-800")
      }
    >
      {children}
    </button>
  );
}

/**
 * Optional refinement: remaining lease, floor and period. Sends exact filters with the next
 * message (no text parsing). Bands with no sales in this town and flat type are disabled.
 */
export function NarrowItDown({ price }: { price: PriceResult }) {
  const { runtime } = useChat();
  const [open, setOpen] = useState(false);
  const [lease, setLease] = useState<LeaseBand | null>(price.filters.lease_band ?? null);
  const [storey, setStorey] = useState<StoreyBand | null>(price.filters.storey_band ?? null);
  const [months, setMonths] = useState(0);
  const breakdown = price.breakdown ?? [];
  if (!breakdown.length) return null;
  const has = (dimension: "lease" | "storey", band: string) => (stat(breakdown, dimension, band)?.volume ?? 0) > 0;
  const f = price.filters;

  const submit = () => {
    const now = new Date();
    const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const filters: PriceFilters = {
      town: f.town,
      flat_type: f.flat_type,
      start_month: months ? shiftMonth(thisMonth, -(months - 1)) : f.start_month,
      end_month: months ? thisMonth : f.end_month,
      lease_band: lease,
      storey_band: storey,
    };
    const flat = /^(\d)\s*ROOM$/i.exec(f.flat_type)?.[1];
    const town = f.town.toLowerCase().replace(/[a-z]+/g, (w) => w[0].toUpperCase() + w.slice(1));
    const leaseText = LEASE.find((l) => l.value === lease)?.label.replace("yrs", "years");
    const storey_ = STOREY.find((s) => s.value === storey)?.label;
    const parts = [
      lease ? `${leaseText} of lease left` : "any remaining lease",
      storey_ ? `${storey_.replace(/ \(.*/, "").toLowerCase()} floors ${storey_.replace(/^[^(]*/, "")}` : "any floor",
      months ? `last ${months} months` : `${monthLabel(f.start_month)} to ${monthLabel(f.end_month)}`,
    ];
    setPendingPriceFilters(filters);
    runtime.thread.append(`Narrow down ${flat ? `${flat}-room` : f.flat_type.toLowerCase()} prices in ${town}: ${parts.join(", ")}`);
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-3 rounded-full border border-coral-300 bg-white px-3 py-1 text-sm hover:bg-coral-50 dark:border-coral-500/60 dark:bg-slate-900 dark:hover:bg-slate-800"
      >
        Narrow it down
      </button>
    );
  }
  return (
    <div className="mt-3 space-y-2 rounded-lg border border-slate-200 p-3 text-xs dark:border-slate-700">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="w-28 text-slate-500">Lease left</span>
        <Chip active={lease === null} onClick={() => setLease(null)}>Any</Chip>
        {LEASE.map((l) => (
          <Chip key={l.value} active={lease === l.value} disabled={!has("lease", l.value)} onClick={() => setLease(l.value)}>
            {l.label}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="w-28 text-slate-500">Floor</span>
        <Chip active={storey === null} onClick={() => setStorey(null)}>Any</Chip>
        {STOREY.map((s) => (
          <Chip key={s.value} active={storey === s.value} disabled={!has("storey", s.value)} onClick={() => setStorey(s.value)}>
            {s.label}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="w-28 text-slate-500">Period</span>
        {PERIODS.map((p) => (
          <Chip key={p.months} active={months === p.months} onClick={() => setMonths(p.months)}>
            {p.label}
          </Chip>
        ))}
      </div>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={submit}
          className="rounded-full bg-coral-500 px-3 py-1 text-sm text-white hover:bg-coral-600"
        >
          Update figures
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-2 text-sm text-slate-500 hover:underline">
          Cancel
        </button>
      </div>
      <p className="text-slate-500">Greyed-out bands had no sales for this town and flat type.</p>
    </div>
  );
}
