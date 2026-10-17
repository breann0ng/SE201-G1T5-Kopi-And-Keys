// Structured content read out of an official source passage, verbatim: tables and
// income-band lists. Nothing is computed or reworded; cells keep the source's wording.

export type SourceTable = { header: string[]; rows: string[][] };
export type IncomeBand = { label: string; low: number; high: number; amount: number; amountText: string };
export type BandList = { title: string; bands: IncomeBand[] };

const SEPARATOR = /^\|?[\s:|-]+\|?$/;

/** Flatten the page markup scraping left in cells: bold markers, footnote sup tags, escapes. */
function cleanCell(cell: string): string {
  return cell
    .replace(/<sup>\s*(.*?)\s*<\/sup>/gi, "$1")
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<\/?[a-z][^>]*>/gi, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\\([[\]()*_|])/g, "$1")
    .trim();
}

function splitRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(cleanCell);
}

/** Every pipe table in the passage. Tables missing the |---| line are still recognised. */
/**
 * Added 2026-10-17: some captured tables have a line break inside a cell
 * ("…who are buying:\nA flat from HDB…"). Markdown ends a row at a line break, so the rest of the
 * cell became a broken one-column row. Rejoin until the row's closing "|" (display only).
 */
export function joinBrokenTableRows(text: string): string {
  const out: string[] = [];
  for (const line of text.split("\n")) {
    const prev = out[out.length - 1];
    if (prev !== undefined && prev.trimStart().startsWith("|") && !prev.trimEnd().endsWith("|") && line.trim()) {
      out[out.length - 1] = `${prev.trimEnd()} ${line.trim()}`;
    } else {
      out.push(line);
    }
  }
  return out.join("\n");
}

export function extractTables(text: string): SourceTable[] {
  const tables: SourceTable[] = [];
  let block: string[] = [];
  const flush = () => {
    const rows = block.filter((l) => !SEPARATOR.test(l.trim())).map(splitRow);
    block = [];
    if (rows.length < 2) return;
    const width = Math.max(...rows.map((r) => r.length));
    const pad = (r: string[]) => [...r, ...Array(width - r.length).fill("")];
    const body = rows.slice(1).map(pad).filter((r) => r.some((cell) => cell));
    if (width >= 2 && body.length) tables.push({ header: pad(rows[0]), rows: body });
  };
  for (const line of joinBrokenTableRows(text).split("\n")) {
    if (line.trim().startsWith("|")) block.push(line);
    else if (block.length) flush();
  }
  if (block.length) flush();
  return tables;
}

const BAND = /^(?:Not more than \$([\d,]+)|\$([\d,]+) to \$([\d,]+))\s+(\$[\d,]+)\s*$/;
const num = (s: string) => Number(s.replace(/[$,]/g, ""));

/** Income bands written as "$6,501 to $7,000 $30,000" lines (HDB's EHG amount tables). */
export function extractBands(text: string): BandList | null {
  const lines = text.split("\n").map((l) => l.trim());
  const bands: IncomeBand[] = [];
  let first = -1;
  lines.forEach((line, i) => {
    const m = BAND.exec(line);
    if (!m) return;
    if (first < 0) first = i;
    const [low, high] = m[1] ? [0, num(m[1])] : [num(m[2]), num(m[3])];
    const label = m[1] ? `Up to $${m[1]}` : `$${m[2]}–$${m[3]}`;
    bands.push({ label, low, high, amount: num(m[4]), amountText: m[4] });
  });
  if (bands.length < 4) return null;
  // The line just above the first band names the two columns, e.g. "Average monthly household income EHG amount".
  const title = first > 0 && !BAND.test(lines[first - 1]) ? lines[first - 1] : "Amount by income band";
  return { title, bands };
}
