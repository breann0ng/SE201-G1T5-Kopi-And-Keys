import type { ChatResponse } from "./api";
import { bandTableMarkdown, extractBands } from "./sourceContent.ts";

const escapeRegex = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const flexibleText = (value: string) => value.trim().split(/\s+/).map(escapeRegex).join("[\\s;]+");

/** Display only: reflow a complete, exact source-band block without dropping surrounding conditions. */
function formatSourceBands(response: ChatResponse): string {
  let text = response.message;
  for (const source of response.citations) {
    if (!text.includes(`[${source.id}]`)) continue;
    const bands = extractBands(source.text);
    if (!bands) continue;
    const rows = flexibleText(bands.sourceRows.join("\n"));
    const full = new RegExp(`${bands.sourceHeader ? `(?:${flexibleText(bands.sourceHeader)}[\\s;]+)?` : ""}${rows}(?![\\d,]|\\.\\d)`, "g");
    text = text.replace(full, () => `\n\n${bandTableMarkdown(bands)}\n\n`);
  }
  return text;
}

export function numberCitations(response: ChatResponse): string {
  let text = formatSourceBands(response);
  response.citations.forEach((source, index) => {
    text = text.split(`[${source.id}]`).join(`[${index + 1}]`);
  });
  return text;
}

/** Copy the answer and its provenance, rather than the main text alone. */
export function answerForClipboard(response: ChatResponse): string {
  const parts = [numberCitations(response)];
  const numberOf = (id: string) => response.citations.findIndex((source) => source.id === id) + 1;
  if (response.overview?.length) {
    parts.push(response.overview.map((item) => `${item.title}: ${item.quote} [${numberOf(item.citation_id)}]`).join("\n\n"));
  }
  if (response.income_notes?.length) {
    parts.push("Income ceilings for your stated income\n\n" + response.income_notes.map((note) =>
      `${note.label}: ${note.message}` +
      (note.conditions?.length ? "\nHDB's conditions:\n" + note.conditions.map((condition) => `- ${condition}`).join("\n") : "") +
      `\nSource: ${note.source_url}`,
    ).join("\n\n"));
  }
  if (response.citations.length) {
    parts.push("Sources\n\n" + response.citations.map((source, index) => {
      const dates = [
        `Snapshot: ${source.snapshot_id}`,
        `Verified: ${source.verified_on}`,
        source.effective_date ? `Effective: ${source.effective_date}` : null,
        source.page_last_updated ? `Page last updated: ${source.page_last_updated}` : null,
      ].filter(Boolean).join("; ");
      return `[${index + 1}] ${source.title}\n${source.source_url}\n${dates}`;
    }).join("\n\n"));
  }
  if (response.mode === "demo") parts.push("SYNTHETIC DEMO EVIDENCE — not actual policy advice.");
  return parts.join("\n\n");
}
