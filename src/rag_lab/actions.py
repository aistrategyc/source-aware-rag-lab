"""A proposed task is inert until the same user confirms it with current permissions."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import psycopg

from rag_lab.retrieval import AccessDenied, StaleContext, membership


def validate_time(now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")


def propose(dsn: str, tenant: str, user: str, source_id: UUID, title: str, now: datetime) -> UUID:
    validate_time(now)
    if not 1 <= len(title.strip()) <= 200:
        raise ValueError("Task title must contain 1–200 characters")
    with psycopg.connect(dsn) as conn:
        membership(conn, tenant, user, write=True)
        source = conn.execute(
            """SELECT version FROM sources
               WHERE tenant_id = %s AND id = %s AND NOT deleted FOR SHARE""",
            (tenant, source_id),
        ).fetchone()
        if not source:
            raise AccessDenied("Source unavailable")
        proposal_id = uuid4()
        conn.execute(
            """INSERT INTO proposals
               (id, tenant_id, actor_id, source_id, source_version, title, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                proposal_id,
                tenant,
                user,
                source_id,
                source[0],
                title.strip(),
                now + timedelta(minutes=10),
            ),
        )
    return proposal_id


def confirm(dsn: str, tenant: str, user: str, proposal_id: UUID, now: datetime) -> UUID:
    validate_time(now)
    with psycopg.connect(dsn) as conn:
        membership(conn, tenant, user, write=True)
        proposal = conn.execute(
            """SELECT source_id, source_version, title, expires_at, confirmed_task_id
               FROM proposals WHERE id = %s AND tenant_id = %s AND actor_id = %s FOR UPDATE""",
            (proposal_id, tenant, user),
        ).fetchone()
        if not proposal:
            raise AccessDenied("Proposal unavailable")
        source_id, version, title, expiry, prior_task = proposal
        source = conn.execute(
            """SELECT version FROM sources
               WHERE tenant_id = %s AND id = %s AND NOT deleted FOR SHARE""",
            (tenant, source_id),
        ).fetchone()
        if not source or source[0] != version:
            raise StaleContext("Source changed; create a new proposal")
        if prior_task:
            return prior_task
        if now >= expiry:
            raise StaleContext("Proposal expired; create a new proposal")
        task_id = uuid4()
        conn.execute(
            "INSERT INTO tasks VALUES (%s, %s, %s, %s, %s)",
            (task_id, tenant, user, source_id, title),
        )
        conn.execute(
            "UPDATE proposals SET confirmed_task_id = %s WHERE id = %s", (task_id, proposal_id)
        )
    return task_id
