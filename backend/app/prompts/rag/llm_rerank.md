Score how well each evidence passage answers the question.

Rules:
- Score each passage from 0 to 10: 10 = directly answers, 0 = irrelevant.
- Do not use outside knowledge. Do not reward length.
- Return ONLY a JSON array of objects in input order: [{"id": <passage id>, "score": <0-10>}]

Question: $question

Passages:
$passages
