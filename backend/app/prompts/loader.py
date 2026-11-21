"""Safe prompt template loading for RAG and agent workflows.

Prompts live as Markdown files under ``app/prompts/`` so they can be reviewed,
versioned and tested like code. Loading is constrained to that directory
(path-traversal rejected) and every template advertises a content hash so
answers can record which prompt version produced them.

Templates use :class:`string.Template` placeholders (``$variable``). ``$$`` is
an escaped literal dollar sign. Missing variables raise
:class:`PromptVariableError` — a silently half-rendered system prompt is worse
than a loud failure.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_ROOT = Path(__file__).resolve().parent

_NAME_RE = re.compile(r"^[a-zA-Z0-9_./-]+\.md$")


class PromptError(RuntimeError):
    pass


class PromptNotFoundError(PromptError):
    pass


class PromptVariableError(PromptError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    path: Path
    text: str
    version: str
    variables: tuple[str, ...]

    def render(self, **values: object) -> str:
        missing = [name for name in self.variables if name not in values or values[name] is None]
        if missing:
            raise PromptVariableError(
                f"prompt '{self.name}' is missing required variables: {', '.join(sorted(missing))}"
            )
        # String.Template.substitute also rejects invalid placeholders.
        return Template(self.text).substitute({key: str(value) for key, value in values.items()})


def _resolve(name: str) -> Path:
    if not _NAME_RE.match(name):
        raise PromptError(f"invalid prompt name: {name!r}")
    path = (PROMPTS_ROOT / name).resolve()
    if PROMPTS_ROOT not in path.parents:
        raise PromptError(f"prompt path escapes prompt root: {name!r}")
    if not path.is_file():
        raise PromptNotFoundError(f"prompt not found: {name}")
    return path


@lru_cache(maxsize=128)
def load_template(name: str) -> PromptTemplate:
    path = _resolve(name)
    text = path.read_text(encoding="utf-8")
    version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    variables = tuple(sorted(set(re.findall(r"\$([a-zA-Z_][a-zA-Z0-9_]*)", text))))
    return PromptTemplate(name=name, path=path, text=text, version=version, variables=variables)


def load_prompt(name: str, **variables: object) -> str:
    """Render a prompt with explicit variables."""
    return load_template(name).render(**variables)


def prompt_version(name: str) -> str:
    return load_template(name).version


def available_prompts() -> list[str]:
    return sorted(str(path.relative_to(PROMPTS_ROOT)).replace("\\", "/") for path in PROMPTS_ROOT.rglob("*.md"))
