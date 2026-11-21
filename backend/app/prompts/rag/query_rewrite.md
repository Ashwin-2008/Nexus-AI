Rewrite the user's question into a concise search query for enterprise retrieval.

Rules:
- Preserve every named entity, number, date, product, and identifier exactly.
- Resolve pronouns only when the conversation excerpt makes the referent unambiguous.
- Remove conversational filler but do not add facts, synonyms, or assumptions.
- Return ONLY the rewritten query on one line. No quotes, no explanation.

Conversation excerpt:
$conversation

Question: $question
