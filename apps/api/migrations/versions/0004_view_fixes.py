"""View fixes: retry/loop paths on each session, index on last_seen.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UP = []
for table in ("sessions", "open_sessions"):
    UP += [
        # Paths (with and without query string) where the session had a retry or a loop. P3 and
        # the journey funnel count distinct sessions from this column, not hourly rows (Flow 4).
        f"alter table {table} add column retry_paths text[] not null default '{{}}'",
        # Old rows: every page of a session with a retry or loop (upper bound until rebuilt).
        f"update {table} set retry_paths = pages_in_order where has_retry or has_loop",
        # Recommendation queries filter on last_seen (Flow 5): the window bound must use an index.
        f"create index {table}_last_seen on {table} (site_id, last_seen)",
    ]

DOWN = []
for table in ("open_sessions", "sessions"):
    DOWN += [
        f"drop index if exists {table}_last_seen",
        f"alter table {table} drop column retry_paths",
    ]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
