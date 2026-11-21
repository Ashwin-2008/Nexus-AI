"""Grounded answer generation."""
from app.rag.generation.generator import GenerationOutcome, Generator
from app.rag.generation.prompts import INSUFFICIENT_EVIDENCE_MESSAGE, build_messages
from app.rag.generation.provider import chat, llm_configured, stream
from app.rag.generation.structured_output import ParsedAnswer, parse_answer, strip_citation_markers

__all__ = [
    "GenerationOutcome",
    "Generator",
    "INSUFFICIENT_EVIDENCE_MESSAGE",
    "ParsedAnswer",
    "build_messages",
    "chat",
    "llm_configured",
    "parse_answer",
    "stream",
    "strip_citation_markers",
]
