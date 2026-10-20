"""Import fixes: arrival time for pair expiry, resume offset, retry count, bucket marks.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UP = [
    # Decision 1b.6: an unpaired row waits from its arrival, not from its event time.
    "alter table events add column imported_at timestamptz not null default now()",
    # Decision 7.9: a large file is imported in slices; lines_done is the resume offset.
    "alter table import_files add column lines_done integer not null default 0",
    # Transient inbox errors: the file goes back to 'new' until retries reach the limit.
    "alter table import_files add column retries integer not null default 0",
    # Import bucket reader: objects already copied (survives a restart, shared by workers).
    """
    create table bucket_objects (
        site_id text not null,
        mark text not null,
        seen_at timestamptz not null default now(),
        primary key (site_id, mark)
    )
    """,
]

DOWN = [
    "drop table if exists bucket_objects",
    "alter table import_files drop column retries",
    "alter table import_files drop column lines_done",
    "alter table events drop column imported_at",
]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
