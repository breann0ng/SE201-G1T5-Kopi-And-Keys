# Topic cards (placeholder)

One reviewed JSON file per discovery topic, loaded by
`backend/kopi_keys/components/topic_cards.py`. No cards exist yet.

Each card follows the `TopicCard` schema. The trigger format below is
illustrative only; the card owner decides the real one:

```json
{
  "id": "remaining-lease",
  "title": "Remaining lease and CPF/grant use",
  "triggers": {"flat_age_years": {"gte": 30}},
  "required_fields": ["flat_age_years"],
  "chunk_ids": ["<policy chunk id from the snapshot>"],
  "question_template": "Have you checked how the remaining lease affects CPF use and grants?"
}
```

Thresholds come from the policy snapshot, not the model. A policy change means
editing a card, then re-checking its chunk IDs.
