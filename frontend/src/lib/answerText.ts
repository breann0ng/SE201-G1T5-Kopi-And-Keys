import type { ChatResponse } from "./api";
import { bandTableMarkdown, extractBands, extractBinaryTable } from "./sourceContent.ts";

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
  let text = formatSelectedBinaryRows(formatSourceBands(response), response);
  response.citations.forEach((source, index) => {
    text = text.split(`[${source.id}]`).join(`[${index + 1}]`);
  });
  return text;
}

/** Reflow two adjacent, source-matched quotes; keep every selected word and citation. */
function formatSelectedBinaryRows(text: string, response: ChatResponse): string {
  const paragraphs = text.split(/\n\n+/);
  const normalize = (value: string) => value.replace(/\*\*/g, "").replace(/\s+/g, " ").trim();
  const cell = (value: string) => value.replace(/\|/g, "\\|");
  for (const source of response.citations) {
    const table = extractBinaryTable(source.text);
    if (!table) continue;
    const citation = ` [${source.id}]`;
    const lead = `${table.header.join(" ")} Yes `;
    for (let i = 0; i + 1 < paragraphs.length; i++) {
      if (!paragraphs[i].endsWith(citation) || !paragraphs[i + 1].endsWith(citation)) continue;
      const yes = normalize(paragraphs[i].slice(0, -citation.length));
      const no = normalize(paragraphs[i + 1].slice(0, -citation.length));
      if (!yes.startsWith(lead) || !no.startsWith("No ")) continue;
      const yesText = yes.slice(lead.length), noText = no.slice(3);
      if (!yesText || !noText || !/[.!?]$/.test(yesText) || !/[.!?]$/.test(noText)) continue;
      if (!table.rows[0][1].startsWith(yesText) || !table.rows[1][1].startsWith(noText)) continue;
      paragraphs[i] = [table.header, ["---", "---"], ["Yes", yesText], ["No", noText]]
        .map((row) => `| ${row.map(cell).join(" | ")} |`).join("\n") + `\n\n[${source.id}]`;
      paragraphs[i + 1] = "";
    }
  }
  return paragraphs.filter(Boolean).join("\n\n");
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
