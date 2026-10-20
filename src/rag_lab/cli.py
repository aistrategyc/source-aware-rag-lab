import argparse
import os
from datetime import UTC, datetime
from uuid import UUID

import psycopg

from rag_lab.actions import confirm, propose
from rag_lab.answer import ExtractiveDemo, answer
from rag_lab.db import migrate

SOURCE = UUID("00000000-0000-0000-0000-000000000001")


def seed(dsn):
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO memberships VALUES ('blue', 'alice', 'editor', true) "
            "ON CONFLICT DO NOTHING"
        )
        conn.execute(
            """INSERT INTO sources(tenant_id, id, title, body) VALUES
               ('blue', %s, 'Delivery runbook', 'Review delayed delivery orders every morning.')
               ON CONFLICT DO NOTHING""",
            (SOURCE,),
        )
        conn.execute(
            """INSERT INTO search_chunks(tenant_id, source_id, source_version, body)
               SELECT tenant_id, id, version, body FROM sources WHERE NOT deleted
               ON CONFLICT (tenant_id, source_id) DO UPDATE
               SET source_version = EXCLUDED.source_version, body = EXCLUDED.body"""
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve → revalidate → cite → propose → confirm")
    parser.add_argument("command", choices=["migrate", "demo"])
    args = parser.parse_args()
    dsn = os.environ["DATABASE_URL"]
    migrate(dsn)
    if args.command == "migrate":
        print("Schema is current.")
        return
    seed(dsn)
    result = answer(dsn, "blue", "alice", "delayed delivery", ExtractiveDemo())
    print("Answer:", result.text)
    print("Sources:", ", ".join(map(str, result.citations)))
    now = datetime.now(UTC)
    proposal = propose(dsn, "blue", "alice", SOURCE, "Review delayed delivery orders", now)
    print("Proposal recorded; no task exists for it yet:", proposal)
    # Deliberate user-confirmation simulation, separate from generation.
    task = confirm(dsn, "blue", "alice", proposal, now)
    print("Simulated user confirmation → task:", task)
    print("Repeated confirmation → same task:", confirm(dsn, "blue", "alice", proposal, now))


if __name__ == "__main__":
    main()
