"""Partitions of events are attached, not created as a child (no ACCESS EXCLUSIVE on events).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# CREATE TABLE ... PARTITION OF takes ACCESS EXCLUSIVE on events: it waits for every open import
# step, and every query on events waits behind it. ATTACH PARTITION takes only SHARE UPDATE
# EXCLUSIVE on events, which does not conflict with readers and writers. The table is made apart
# (LIKE) with a range check, so the attach does not scan; the indexes of events are made on the
# empty table by the attach. Old partitions are detached and dropped by the cleanup job from
# Python (DETACH ... CONCURRENTLY cannot run in a function), so the SQL drop function goes.
ENSURE = """
create or replace function ensure_events_partition(day date) returns text
language plpgsql as $$
declare
    part text = 'events_' || to_char(day, 'YYYYMMDD');
    lo timestamptz = (day::timestamp at time zone 'UTC');
    hi timestamptz = ((day + 1)::timestamp at time zone 'UTC');
    existed boolean;
begin
    if exists (
        select 1 from pg_inherits
        where inhparent = 'events'::regclass and inhrelid = to_regclass(part)
    ) then
        return part;
    end if;
    perform pg_advisory_xact_lock(
        hashtext('ensure_events_partition'), to_char(day, 'YYYYMMDD')::int
    );
    if exists (
        select 1 from pg_inherits
        where inhparent = 'events'::regclass and inhrelid = to_regclass(part)
    ) then
        return part;
    end if;
    existed = to_regclass(part) is not null;
    if not existed then
        execute 'create table ' || quote_ident(part)
            || ' (like events including defaults including constraints)';
        execute 'alter table ' || quote_ident(part) || ' add constraint '
            || quote_ident(part || '_range') || ' check (ts >= ' || quote_literal(lo::text)
            || ' and ts < ' || quote_literal(hi::text) || ')';
    end if;
    execute 'alter table events attach partition ' || quote_ident(part)
        || ' for values from (' || quote_literal(lo::text) || ') to ('
        || quote_literal(hi::text) || ')';
    return part;
end
$$
"""

OLD_ENSURE = """
create or replace function ensure_events_partition(day date) returns text
language plpgsql as $$
declare
    part text = 'events_' || to_char(day, 'YYYYMMDD');
    lo timestamptz = (day::timestamp at time zone 'UTC');
    hi timestamptz = ((day + 1)::timestamp at time zone 'UTC');
begin
    if to_regclass(part) is not null then
        return part;
    end if;
    perform pg_advisory_xact_lock(
        hashtext('ensure_events_partition'), to_char(day, 'YYYYMMDD')::int
    );
    if to_regclass(part) is not null then
        return part;
    end if;
    execute 'create table ' || quote_ident(part) || ' partition of events for values from ('
        || quote_literal(lo::text) || ') to (' || quote_literal(hi::text) || ')';
    return part;
end
$$
"""

OLD_DROP = """
create function drop_events_partitions_older_than(keep_days integer) returns integer
language plpgsql as $$
declare
    r record;
    dropped integer = 0;
    cutoff date = (now() at time zone 'UTC')::date - keep_days;
begin
    for r in
        select c.relname
        from pg_inherits i join pg_class c on c.oid = i.inhrelid
        where i.inhparent = 'events'::regclass and c.relname ~ '^events_[0-9]{8}$'
    loop
        if to_date(substr(r.relname, 8), 'YYYYMMDD') < cutoff then
            execute 'drop table ' || quote_ident(r.relname);
            dropped = dropped + 1;
        end if;
    end loop;
    return dropped;
end
$$
"""


def upgrade() -> None:
    op.execute(ENSURE)
    op.execute("drop function if exists drop_events_partitions_older_than(integer)")


def downgrade() -> None:
    op.execute(OLD_ENSURE)
    op.execute(OLD_DROP)
