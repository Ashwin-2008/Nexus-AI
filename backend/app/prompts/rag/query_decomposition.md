Break the question into at most $max_subqueries independent retrieval queries.

Rules:
- Each subquery must be answerable by document/email/database evidence.
- Keep entities, numbers, and dates exact.
- Do not invent facts. Do not include redundant subqueries.
- Return ONLY a JSON array of strings, e.g. ["first query", "second query"].

Question: $question
