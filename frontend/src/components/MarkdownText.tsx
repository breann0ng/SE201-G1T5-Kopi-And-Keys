import type { TextMessagePartComponent } from "@assistant-ui/react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { joinBrokenTableRows } from "../lib/sourceContent";

/**
 * Renders an answer's Markdown (bold, lists, headings, tables) as formatted text.
 * Raw HTML is never rendered: react-markdown escapes it, and leftovers that the
 * policy pages carry into quoted text (<sup>…</sup>, <br>) are flattened first.
 */
function tidy(text: string): string {
  return joinBrokenTableRows(text)
    .replace(/<sup>\s*(.*?)\s*<\/sup>/gi, "$1") // footnote markers: "Prime<sup>[1]</sup>" -> "Prime[1]"
    .replace(/<br\s*\/?>/gi, " ")
    // Leftover download-link labels from the official pages, e.g. "(PDF, 198KB)"; the link itself
    // was not captured (added 2026-10-17). Display only; the verifier checks the original.
    .replace(/\s*\((?:PDF|DOCX?|XLSX?)\s*,\s*[\d.]+\s*[KM]B\)/gi, "")
    // Bulleted lists inside HDB table cells were flattened when captured, so separate amounts
    // ran together ("exceed: $16,000 $24,000 if ..."). Put a separator back only where an item that
    // starts with an amount runs into the next amount; "between $3,000 and $4,000" is left alone
    // (added 2026-10-18). Display only.
    .replace(/(\$\d[\d,]*(?:\.\d+)?(?:[^$:;.\n|]*[\w)])?)(?<!\b(?:and|or|to|than|from|between|of|by))\s+(?=\$\d)/g, "$1; ")
    .replace(/<\/?[a-z][^>]*>/gi, "") // any other stray tag
    .replace(/\n{3,}/g, "\n\n");
}

const components: Components = {
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  h1: ({ children }) => <h3 className="mt-3 mb-1 text-base font-semibold">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-3 mb-1 text-base font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-3 mb-1 font-semibold">{children}</h4>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-brand-600 underline dark:text-brand-100">
      {children}
    </a>
  ),
  hr: () => <hr className="my-3 border-slate-200 dark:border-slate-700" />,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-100 dark:bg-slate-800">{children}</thead>,
  th: ({ children }) => <th className="px-3 py-2 align-top font-semibold">{children}</th>,
  td: ({ children }) => (
    <td className="border-t border-slate-200 px-3 py-2 align-top dark:border-slate-700">{children}</td>
  ),
  code: ({ children }) => (
    <code className="rounded bg-slate-100 px-1 py-0.5 text-[0.9em] dark:bg-slate-800">{children}</code>
  ),
};

/** The same rendering for any official text, e.g. related passages (added 2026-10-17). */
export function SourceMarkdown({ text }: { text: string }) {
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {tidy(text)}
    </Markdown>
  );
}

export const MarkdownText: TextMessagePartComponent = ({ text }) => (
  <div className="leading-relaxed">
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {tidy(text)}
    </Markdown>
  </div>
);
