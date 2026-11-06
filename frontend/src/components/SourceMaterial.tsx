import { ChevronDown, Table2, TrendingDown } from "lucide-react";
import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts";
import type { PolicyPassage } from "../lib/api";
import { bandTable, extractBands, extractTables, type BandList, type SourceTable } from "../lib/sourceContent";
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
          {bands && (
            <div className="space-y-2">
              <p className="text-xs text-slate-500">
                {bands.scope ? `Source scope: ${bands.scope}. ` : ""}
                Source table for reference; this does not determine your eligibility or grant amount.
              </p>
              <TableExpander table={bandTable(bands)} passage={p} n={numberOf(p.id)} />
              {bands.incomeBasis !== "unknown" && (
                <Collapsible className="rounded-lg border border-slate-200 dark:border-slate-700">
                  <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-600 dark:text-slate-300">
                    <TrendingDown size={14} /> View source chart [{numberOf(p.id)}]
                    <ChevronDown size={14} className="ml-auto transition-transform group-data-[state=open]:rotate-180" />
                  </CollapsibleTrigger>
                  <CollapsibleContent><BandChart bands={bands} passage={p} n={numberOf(p.id)} /></CollapsibleContent>
                </Collapsible>
              )}
            </div>
          )}
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
} satisfies ChartConfig;

const sgd = (n: number) => `$${n.toLocaleString("en-SG")}`;

function BandChart({ bands, passage, n }: { bands: BandList; passage: PolicyPassage; n: number }) {
  return (
    <figure className="p-3">
      <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
        <TrendingDown size={14} className="text-coral-500" /> {bands.title}
      </p>
      <ChartContainer config={chartConfig} className="aspect-auto w-full" style={{ height: bands.bands.length * 28 + 40 }}>
        <BarChart data={bands.bands} layout="vertical" margin={{ top: 4, right: 58, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} />
          <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v: number) => `$${v / 1000}k`} />
          <YAxis dataKey="label" type="category" tickLine={false} axisLine={false} width={150} interval={0} />
          <ChartTooltip cursor content={<ChartTooltipContent formatter={(v) => sgd(Number(v))} />} />
          <Bar dataKey="amount" fill="var(--color-amount)" radius={[0, 3, 3, 0]}>
            <LabelList dataKey="amountText" position="right" fontSize={11} />
          </Bar>
        </BarChart>
      </ChartContainer>
      <figcaption className="mt-1 text-xs text-slate-500">
        {bands.incomeBasis === "half_household" && "Income bands represent half of average monthly household income, as stated in the source. "}
        Grant amounts are in SGD. This chart is drawn from source data, not a personalised estimate.{" "}
        <SourceCaption passage={passage} n={n} />
      </figcaption>
    </figure>
  );
}
