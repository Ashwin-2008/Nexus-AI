"""Optional LLM entailment pass for claims the lexical matcher cannot decide."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.rag.types import EvidenceChunk

logger = logging.getLogger(__name__)
_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "rag" / "verify_claims.md"


def _prompt_text() -> str:
    try:
        return _PROMPT.read_text(encoding="utf-8")
    except OSError:
        return (
            "Decide whether each claim is supported by its passages. Judge meaning, not keywords. "
            "Return ONLY JSON: [{\"claim\": 1, \"verdict\": \"supported\", \"score\": 0.9, \"reason\": \"...\"}]"
        )


def _parse_json_array(text: str) -> list[dict]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        value = json.loads(cleaned[start : end + 1])
    except (TypeError, ValueError):
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def verify_claims_with_llm(
    claims: list[tuple[str, list[EvidenceChunk]]],
    *,
    max_claims: int = 10,
) -> dict[int, dict]:
    """Return ``{claim_index: {verdict, score, reason}}`` for *claims*.

    Callers pass only ambiguous claims. Failure returns an empty mapping so the
    deterministic decision remains authoritative.
    """
    if not claims:
        return {}
    try:
        from app.rag.generation.provider import chat, llm_configured

        if not llm_configured():
            return {}
    except Exception:  # noqa: BLE001
        return {}

    outcome: dict[int, dict] = {}
    for offset in range(0, len(claims[:max_claims]), 5):
        batch = claims[offset : offset + 5]
        payload: list[dict] = []
        for index, (claim, evidence) in enumerate(batch, start=1):
            passages = []
            for rank, item in enumerate(evidence[:4], start=1):
                passages.append(
                    {
                        "passage": rank,
                        "title": item.document_filename,
                        "text": (item.text or "")[:1800],
                    }
                )
            payload.append({"claim": index, "text": claim, "passages": passages})
        try:
            result = chat(
                [
                    {"role": "system", "content": _prompt_text()},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.0,
                max_tokens=1200,
            )
            parsed = _parse_json_array(result.text or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM claim verification failed: %s", exc)
            continue
        for item in parsed:
            try:
                local = int(item.get("claim")) - 1
            except (TypeError, ValueError):
                continue
            if not 0 <= local < len(batch):
                continue
            verdict = str(item.get("verdict") or "").strip().lower()
            if verdict not in {"supported", "partial", "unsupported", "conflicting"}:
                continue
            try:
                score = max(0.0, min(1.0, float(item.get("score", 0.5))))
            except (TypeError, ValueError):
                score = 0.5
            outcome[offset + local] = {
                "verdict": verdict,
                "score": score,
                "reason": str(item.get("reason") or "")[:240],
            }
    return outcome


__all__ = ["verify_claims_with_llm"]