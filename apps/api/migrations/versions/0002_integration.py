"""Integration fixes: in_views flag, pairing identity, exact recommendation score.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UP = [
    # Decision 4.1: new work = events with in_views = false. Cost follows new events,
    # not history.
    "alter table events add column in_views boolean not null default false",
    # Events that already have a session row are done (old data from before this migration).
    """
    update events e set in_views = true
    where exists (
        select 1 from session_events se
        where se.site_id = e.site_id and se.event_id = e.id and se.event_ts = e.ts
    )
    """,
    """
    create index events_not_in_views on events (site_id, ts)
        where not in_views and pair_state <> 'pending'
    """,
    # Pairing: the origin row is deleted on pairing. The paired row keeps its identity, so a
    # re-import of the origin file does not insert the merged lines again.
    "alter table events add column origin_line_key text",
    "alter table events add column origin_file_id uuid",
    """
    create index events_origin_line_key on events (site_id, origin_line_key)
        where origin_line_key is not null
    """,
    # Recommendations: a score such as 3 x 2 x 3 x 0.6 = 10.8 must be stored exactly.
    "alter table recommendations alter column score type numeric(8, 1)",
]

DOWN = [
    "alter table recommendations alter column score type integer using round(score)::integer",
    "drop index if exists events_origin_line_key",
    "alter table events drop column origin_file_id",
    "alter table events drop column origin_line_key",
    "drop index if exists events_not_in_views",
    "alter table events drop column in_views",
]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
