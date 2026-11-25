Score how well each evidence passage answers the question by MEANING, not by
shared keywords. A passage can answer a paraphrase using different words;
score it highly. A passage that repeats the question words but does not contain
the answer should score low.

Rules:
- Score each passage from 0 to 10: 10 = directly and completely answers, 0 = irrelevant.
- Use only the passage. Do not use outside knowledge. Do not reward length.
- Return ONLY a JSON array of objects in input order: [{"id": <passage id>, "score": <0-10>}]

Question: $question

Passages:
$passages
