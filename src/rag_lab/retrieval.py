"""Search returns candidates. Only the source database can authorize context."""

from dataclasses import dataclass
from uuid import UUID

import psycopg


class AccessDenied(Exception):
    pass


class StaleContext(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    source_id: UUID
    version: int


@dataclass(frozen=True)
class Context:
    source_id: UUID
    version: int
    title: str
    text: str


def membership(conn, tenant: str, user: str, *, write: bool = False):
    row = conn.execute(
        """SELECT role FROM memberships
           WHERE tenant_id = %s AND user_id = %s AND active FOR SHARE""",
        (tenant, user),
    ).fetchone()
    if not row or (write and row[0] != "editor"):
        raise AccessDenied("Workspace is unavailable or permission was revoked")


def search(dsn: str, tenant: str, user: str, question: str) -> list[Candidate]:
    if not 1 <= len(question.strip()) <= 500:
        raise ValueError("Question must contain 1–500 characters")
    with psycopg.connect(dsn) as conn:
        membership(conn, tenant, user)
        rows = conn.execute(
            """SELECT source_id, source_version FROM search_chunks,
                      websearch_to_tsquery('english', %s) query
               WHERE tenant_id = %s AND search_vector @@ query
               ORDER BY ts_rank(search_vector, query) DESC, source_id LIMIT 5""",
            (question, tenant),
        ).fetchall()
    return [Candidate(*row) for row in rows]


def revalidate(dsn: str, tenant: str, user: str, candidates: list[Candidate]) -> list[Context]:
    contexts = []
    seen = set()
    with psycopg.connect(dsn) as conn:
        membership(conn, tenant, user)
        for candidate in candidates[:5]:
            if candidate.source_id in seen:
                continue
            seen.add(candidate.source_id)
            row = conn.execute(
                """SELECT version, title, body FROM sources
                   WHERE tenant_id = %s AND id = %s AND NOT deleted FOR SHARE""",
                (tenant, candidate.source_id),
            ).fetchone()
            if row and row[0] == candidate.version:
                # Text comes from the canonical source, never from a search payload.
                contexts.append(Context(candidate.source_id, row[0], row[1], row[2][:4000]))
    return contexts
