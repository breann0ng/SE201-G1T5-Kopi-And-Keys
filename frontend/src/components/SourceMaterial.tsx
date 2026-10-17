import { ChevronDown, Table2, TrendingDown } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts";
import type { PolicyPassage } from "../lib/api";
import { useProfile } from "../lib/profile";
import { extractBands, extractTables, type BandList, type SourceTable } from "../lib/sourceContent";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "./ui/chart";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";

/**
 * Source material behind an answer, shown exactly as captured in the policy snapshot:
 * the full tables in each cited passage (collapsed by default) and, for HDB's income-band
 * tables, a chart of amount by band. Nothing here is written or computed by the AI.
 */
export function SourceMaterial({ passages, numberOf }: { passages: PolicyPassage[]; numberOf: (id: string) => number }) {
  const items = passages.flatMap((p) => {
    const bands = extractBands(p.text);
    const tables = extractTables(p.text);
    return bands || tables.length ? [{ p, bands, tables }] : [];
  });
  if (!items.length) return null;
  return (
    <div className="mt-3 space-y-2">
      {items.map(({ p, bands, tables }) => (
        <div key={p.id} className="space-y-2">
          {bands && <BandChart bands={bands} passage={p} n={numberOf(p.id)} />}
          {tables.map((table, i) => (
            <TableExpander key={i} table={table} passage={p} n={numberOf(p.id)} />
          ))}
        </div>
      ))}
    </div>
  );
}

function SourceCaption({ passage, n }: { passage: PolicyPassage; n: number }) {
  return (
    <>
      Official wording from source [{n}]:{" "}
      <a href={passage.source_url} target="_blank" rel="noreferrer" className="underline">
        {passage.title}
      </a>
    </>
  );
}

function TableExpander({ table, passage, n }: { table: SourceTable; passage: PolicyPassage; n: number }) {
  return (
    <Collapsible className="rounded-lg border border-slate-200 dark:border-slate-700">
      <CollapsibleTrigger className="group flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:text-brand-600 dark:text-slate-300">
        <Table2 size={14} className="text-coral-500" />
        Show full table from source [{n}]
        <ChevronDown size={14} className="ml-auto transition-transform group-data-[state=open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 pb-3">
        <Table>
          <TableHeader>
            <TableRow>
              {table.header.map((h, i) => (
                <TableHead key={i}>{h}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {table.rows.map((row, r) => (
              <TableRow key={r}>
                {row.map((cell, c) => (
                  <TableCell key={c} className={c === 0 ? "font-medium" : undefined}>
                    {cell}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
          <TableCaption>
            <SourceCaption passage={passage} n={n} />
          </TableCaption>
        </Table>
      </CollapsibleContent>
    </Collapsible>
  );
}

const chartConfig = {
  amount: { label: "Grant amount", color: "var(--color-brand-200)" },
  yours: { label: "Your band", color: "var(--color-coral-500)" },
} satisfies ChartConfig;

const sgd = (n: number) => `$${n.toLocaleString("en-SG")}`;

function BandChart({ bands, passage, n }: { bands: BandList; passage: PolicyPassage; n: number }) {
  const { profile } = useProfile();
  const income = profile.household_income;
  const yours = income === null ? -1 : bands.bands.findIndex((b) => income >= b.low && income <= b.high);
  return (
    <figure className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
      <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
        <TrendingDown size={14} className="text-coral-500" /> {bands.title}
      </p>
      <ChartContainer config={chartConfig} className="aspect-auto h-56 w-full">
        <BarChart data={bands.bands} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={12} />
          <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => `$${v / 1000}k`} />
          <ChartTooltip cursor content={<ChartTooltipContent formatter={(v) => sgd(Number(v))} />} />
          <Bar dataKey="amount" radius={3}>
            {bands.bands.map((b, i) => (
              <Cell key={b.label} fill={i === yours ? "var(--color-yours)" : "var(--color-amount)"} />
            ))}
          </Bar>
        </BarChart>
      </ChartContainer>
      <figcaption className="mt-1 text-xs text-slate-500">
        {yours >= 0 ? (
          <>
            Your stated income ({sgd(income as number)}) falls in the {bands.bands[yours].label} band:{" "}
            <strong>{bands.bands[yours].amountText}</strong> in this table. Only HDB's HFE letter confirms what you
            receive.{" "}
          </>
        ) : null}
        <SourceCaption passage={passage} n={n} />
      </figcaption>
    </figure>
  );
}
