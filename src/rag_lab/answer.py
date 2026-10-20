from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from rag_lab.retrieval import Candidate, Context, StaleContext, revalidate, search


@dataclass(frozen=True)
class Answer:
    text: str
    citations: tuple[UUID, ...]


class Generator(Protocol):
    def generate(self, question: str, contexts: tuple[Context, ...]) -> Answer: ...


class ExtractiveDemo:
    """Deterministic stand-in for an LLM. No network, model weights or tool execution."""

    def generate(self, question: str, contexts: tuple[Context, ...]) -> Answer:
        first = contexts[0]
        return Answer(f"{first.title}: {first.text}", (first.source_id,))


def answer(dsn: str, tenant: str, user: str, question: str, generator: Generator) -> Answer:
    candidates = search(dsn, tenant, user, question)
    contexts = revalidate(dsn, tenant, user, candidates)
    if not contexts:
        return Answer("No current, accessible source found.", ())
    result = generator.generate(question, tuple(contexts))
    if not result.citations or not set(result.citations) <= {c.source_id for c in contexts}:
        raise ValueError("Generator returned missing or unknown citations")
    if not result.text.strip() or len(result.text) > 20_000:
        raise ValueError("Generator returned an invalid answer")
    # A slow provider may finish after permissions or source content have changed.
    current = revalidate(dsn, tenant, user, [Candidate(c.source_id, c.version) for c in contexts])
    if {(c.source_id, c.version) for c in current} != {(c.source_id, c.version) for c in contexts}:
        raise StaleContext("Sources changed while generating the answer; run retrieval again")
    return result
