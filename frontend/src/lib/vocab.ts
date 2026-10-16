// Citizenship options come from the shared vocabulary (data/schema/vocab.json, DRAFT),
// so the UI, topic cards and chunk tags all use the same values.
import vocab from "../../../data/schema/vocab.json";

type VocabValue = { display: string };

export const citizenshipOptions = Object.entries(
  vocab.fields.citizenship.values as Record<string, VocabValue>,
).map(([value, v]) => ({ value, label: v.display }));
