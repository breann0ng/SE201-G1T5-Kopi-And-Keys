import { SourceMarkdown } from "./MarkdownText";
import { ChevronDown, ExternalLink, LayoutList, Library, Scale } from "lucide-react";
import type { IncomeNote, OverviewItem, PolicyPassage } from "../lib/api";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";

/** Broad questions: one row per scheme, each an official sentence quoted verbatim with its source. */
export function OverviewTable({ items, numberOf }: { items: OverviewItem[]; numberOf: (id: string) => number }) {
  return (
    <div className="mt-3">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
        <LayoutList size={14} className="text-coral-500" /> Overview
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-1/3">Scheme</TableHead>
            <TableHead>What the official source says</TableHead>
            <TableHead className="w-14 text-center">Source</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.card_id}>
              <TableCell className="font-medium">{item.title}</TableCell>
              <TableCell className="whitespace-pre-line">“{item.quote.replace(/\n- /g, "\n")}”</TableCell>
              <TableCell className="text-center">[{numberOf(item.citation_id)}]</TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableCaption>
          Quoted word for word from HDB and CPF pages. Whether you qualify, and for how much, is confirmed only by
          HDB's HFE letter.
        </TableCaption>
      </Table>
    </div>
  );
}

/** Retrieved official passages the answer didn't quote, collapsed, for readers who want more context. */
export function RelatedPassages({ passages }: { passages: PolicyPassage[] }) {
  if (!passages.length) return null;
  return (
    <Collapsible className="mt-3 rounded-lg border border-slate-200 dark:border-slate-700">
      <CollapsibleTrigger className="group flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:text-brand-600 dark:text-slate-300">
        <Library size={14} className="text-coral-500" />
        Related official passages ({passages.length})
        <ChevronDown size={14} className="ml-auto transition-transform group-data-[state=open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 px-3 pb-3">
        {passages.map((p) => (
          <div key={p.id} className="border-t border-slate-200 pt-2 text-sm dark:border-slate-700">
            <a href={p.source_url} target="_blank" rel="noreferrer" className="font-medium text-brand-600 hover:underline dark:text-brand-100">
              {p.title}
            </a>
            <div className="mt-1 max-h-72 overflow-y-auto pr-1 leading-relaxed text-slate-600 dark:text-slate-300">
              <SourceMarkdown text={p.text} />
            </div>
          </div>
        ))}
        <p className="text-xs text-slate-500">
          Retrieved for this question but not quoted in the answer. Shown exactly as captured from the official pages.
        </p>
      </CollapsibleContent>
    </Collapsible>
  );
}

/** Income ceilings for the grants in play, compared with the income in "Your situation". */
export function IncomeNotes({ notes }: { notes: IncomeNote[] }) {
  if (!notes.length) return null;
  return (
    <div className="mt-3 rounded-lg border border-coral-300 bg-coral-50 p-3 text-sm dark:border-coral-500/40 dark:bg-coral-500/10">
      <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-700 dark:text-slate-200">
        <Scale size={14} className="text-coral-600" /> Income ceilings for your stated income
      </p>
      <ul className="space-y-1.5">
        {notes.map((n) => (
          <li key={n.scheme}>
            <span className="font-medium">{n.label}:</span> ceiling ${n.ceiling}.{" "}
            <span className={n.within_ceiling ? "" : "font-medium text-amber-700 dark:text-amber-300"}>
              {n.message}
            </span>{" "}
            <a href={n.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-brand-600 underline dark:text-brand-100">
              HDB source <ExternalLink size={11} />
            </a>
            {n.conditions && n.conditions.length > 0 && (
              <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                <span className="font-medium">HDB&apos;s conditions:</span>
                <ul className="mt-0.5 list-disc space-y-0.5 pl-5">
                  {n.conditions.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
