"""Initial schema: every table of the pipeline.

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    # ---- Import: import files and rejects ----
    """
    create table import_files (
        id uuid primary key default gen_random_uuid(),
        site_id text not null,
        source text not null check (source in ('origin', 'cdn')),
        entry text not null default 'ingest'
            check (entry in ('ingest', 'upload', 'cli', 'bucket')),
        object_key text not null,
        sha256 text not null,
        size_bytes bigint not null,
        priority text not null default 'live' check (priority in ('live', 'backfill')),
        status text not null default 'new'
            check (status in ('new', 'importing', 'success', 'failed')),
        received_at timestamptz not null default now(),
        started_at timestamptz,
        finished_at timestamptz,
        lines_total integer not null default 0,
        lines_imported integer not null default 0,
        lines_rejected integer not null default 0,
        lines_duplicate integer not null default 0,
        min_ts timestamptz,
        max_ts timestamptz,
        error text,
        attempts integer not null default 0,
        object_deleted_at timestamptz,
        unique (site_id, sha256)
    )
    """,
    "create index import_files_queue on import_files (site_id, status, priority, received_at)",
    "create index import_files_received on import_files (site_id, received_at desc)",
    """
    create table import_rejects (
        id bigint generated always as identity primary key,
        file_id uuid not null references import_files (id) on delete cascade,
        site_id text not null,
        line_no integer not null,
        reason text not null
    )
    """,
    "create index import_rejects_file on import_rejects (file_id, line_no)",
    # ---- Verify and Classify: verdicts (append-only) ----
    """
    create table verdicts (
        id bigint generated always as identity primary key,
        site_id text not null,
        client_key text not null,
        edge_signal text not null default 'none' check (edge_signal in ('bot', 'human', 'none')),
        user_agent text,
        client_ip inet,
        claimed_agent text,
        registry_category text,
        verdict text not null
            check (verdict in ('VERIFIED', 'CLAIMED', 'UNVERIFIED', 'SPOOFED', 'UNKNOWN')),
        method text not null default 'none' check (method in ('ip_list', 'rdns', 'none')),
        evidence text,
        registry_version text,
        ip_snapshot_version text,
        checked_at timestamptz not null default now(),
        traffic_class smallint check (traffic_class between 1 and 6),
        confidence text check (confidence in ('high', 'medium', 'low')),
        rule_id text,
        rule_version text,
        class_evidence text,
        flags text[] not null default '{}',
        ua_type text,
        classified_at timestamptz
    )
    """,
    "create index verdicts_current on verdicts (site_id, client_key, edge_signal, id desc)",
    """
    create index verdicts_unclassified on verdicts (site_id, id)
        where traffic_class is null
    """,
    "create index verdicts_agent on verdicts (site_id, claimed_agent, id desc)",
    # ---- Verify: IP list snapshots ----
    """
    create table ip_list_snapshots (
        source text not null,
        version text not null,
        fetched_at timestamptz not null default now(),
        prefixes cidr[] not null default '{}',
        primary key (source, version)
    )
    """,
    "create index ip_list_snapshots_latest on ip_list_snapshots (source, fetched_at desc)",
    # ---- Import and pairing: events, daily partitions ----
    """
    create table events (
        id bigint generated always as identity,
        site_id text not null,
        ts timestamptz not null,
        file_id uuid,
        line_no integer,
        source text not null check (source in ('origin', 'cdn', 'paired')),
        method text,
        host text,
        path text not null,
        status smallint,
        edge_status smallint,
        origin_status smallint,
        bytes_sent bigint,
        response_time_ms integer,
        referrer text,
        client_ip inet,
        user_agent text,
        client_key text,
        request_id text,
        edge_request_id text,
        edge_signal text not null default 'none' check (edge_signal in ('bot', 'human', 'none')),
        line_key text not null,
        pair_state text not null default 'single'
            check (pair_state in ('pending', 'paired', 'single')),
        cdn_bypass boolean not null default false,
        verdict_id bigint,
        primary key (site_id, ts, id)
    ) partition by range (ts)
    """,
    "create index events_ts_brin on events using brin (ts)",
    "create index events_client on events (site_id, client_key, ts)",
    "create unique index events_dedupe on events (site_id, source, line_key, ts)",
    "create index events_id on events (id)",
    "create index events_file on events (site_id, file_id)",
    """
    create index events_pending on events (site_id, edge_request_id, ts)
        where pair_state = 'pending'
    """,
    """
    create index events_no_verdict on events (site_id, client_key)
        where verdict_id is null and pair_state <> 'pending'
    """,
    """
    create function ensure_events_partition(day date) returns text
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
    """,
    """
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
    """,
    # ---- Activity reconstruction: sessions (closed), open_sessions, session_events ----
    """
    create table sessions (
        site_id text not null,
        session_id text not null,
        version integer not null default 1,
        client_key text not null,
        verdict_id bigint,
        claimed_agent text,
        user_agent text,
        client_ip inet,
        edge_signal text not null default 'none',
        traffic_class smallint,
        confidence text,
        started timestamptz not null,
        last_seen timestamptz not null,
        requests integer not null default 0,
        distinct_pages integer not null default 0,
        pages_in_order text[] not null default '{}',
        key_pages_visited integer not null default 0,
        reached_conversion boolean not null default false,
        has_retry boolean not null default false,
        has_loop boolean not null default false,
        retries integer not null default 0,
        shared_ip boolean not null default false,
        gaps text[] not null default '{}',
        status_counts jsonb not null default '{}',
        journeys_reached jsonb not null default '{}',
        primary key (site_id, session_id)
    )
    """,
    "create index sessions_started on sessions (site_id, started desc)",
    "create index sessions_client on sessions (site_id, client_key, started)",
    "create index sessions_class on sessions (site_id, traffic_class, started)",
    "create table open_sessions (like sessions including all)",
    """
    create table session_events (
        site_id text not null,
        session_id text not null,
        event_id bigint not null,
        event_ts timestamptz not null,
        seq integer not null,
        primary key (site_id, session_id, seq)
    )
    """,
    "create index session_events_event on session_events (site_id, event_id)",
    # ---- Activity reconstruction: hourly view tables ----
    """
    create table page_stats (
        site_id text not null,
        hour timestamptz not null,
        path text not null,
        traffic_class smallint not null,
        tags text[] not null default '{}',
        requests integer not null default 0,
        sessions integer not null default 0,
        clients integer not null default 0,
        median_bytes bigint,
        n_2xx integer not null default 0,
        n_3xx integer not null default 0,
        n_403 integer not null default 0,
        n_429 integer not null default 0,
        n_4xx integer not null default 0,
        n_5xx integer not null default 0,
        retries integer not null default 0,
        primary key (site_id, hour, path, traffic_class)
    )
    """,
    "create index page_stats_path on page_stats (site_id, path, hour)",
    """
    create table journey_steps (
        site_id text not null,
        hour timestamptz not null,
        journey_id text not null,
        traffic_class smallint not null,
        step_no integer not null,
        step_path text not null,
        sessions_reached integer not null default 0,
        sessions_retry_or_loop integer not null default 0,
        primary key (site_id, hour, journey_id, traffic_class, step_no)
    )
    """,
    """
    create table agents (
        site_id text not null,
        hour timestamptz not null,
        claimed_agent text not null,
        traffic_class smallint not null,
        verification text,
        confidence text,
        first_seen timestamptz,
        last_seen timestamptz,
        requests integer not null default 0,
        sessions integer not null default 0,
        distinct_pages integer not null default 0,
        top_paths text[] not null default '{}',
        primary key (site_id, hour, claimed_agent, traffic_class)
    )
    """,
    # ---- Recommendations ----
    """
    create table recommendation_runs (
        id bigint generated always as identity primary key,
        site_id text not null,
        window_size text not null,
        window_start timestamptz not null,
        window_end timestamptz not null,
        rule_version text,
        prompt_version text,
        model text,
        status text not null default 'running' check (status in ('running', 'success', 'failed')),
        started_at timestamptz not null default now(),
        finished_at timestamptz,
        counts jsonb not null default '{}',
        error text
    )
    """,
    "create index recommendation_runs_site on recommendation_runs (site_id, id desc)",
    """
    create table recommendations (
        id bigint generated always as identity primary key,
        run_id bigint not null references recommendation_runs (id) on delete cascade,
        site_id text not null,
        stable_id text not null,
        rank integer,
        pattern text not null,
        target text not null,
        journey_id text,
        score integer not null,
        impact smallint not null,
        frequency smallint not null,
        severity smallint not null,
        confidence_factor numeric(3, 1) not null,
        confidence text not null check (confidence in ('high', 'medium', 'low')),
        factor_reasons jsonb not null default '{}',
        recommended_test text,
        reason text,
        evidence jsonb not null default '{}',
        sessions_count integer not null default 0,
        events_count integer not null default 0,
        potential_issue text,
        suggested_validation text,
        next_action text,
        text_source text not null default 'template' check (text_source in ('llm', 'template')),
        model text,
        prompt_version text,
        change text check (change in ('new', 'open', 'gone')),
        bundle jsonb not null default '{}'
    )
    """,
    "create index recommendations_run on recommendations (run_id, rank)",
    "create index recommendations_stable on recommendations (site_id, stable_id, run_id)",
    """
    create table llm_text_cache (
        bundle_hash text primary key,
        site_id text not null,
        text jsonb not null,
        model text,
        prompt_version text,
        created_at timestamptz not null default now()
    )
    """,
    # ---- Pipeline: runs, fair turns, alerts ----
    """
    create table pipeline_runs (
        id uuid primary key default gen_random_uuid(),
        site_id text not null,
        lane text not null check (lane in ('fast', 'slow')),
        started_at timestamptz not null default now(),
        finished_at timestamptz,
        status text not null default 'running' check (status in ('running', 'success', 'failed')),
        failed_step text,
        error text,
        counts jsonb not null default '{}'
    )
    """,
    "create index pipeline_runs_site on pipeline_runs (site_id, lane, started_at desc)",
    """
    create table site_work (
        site_id text not null,
        lane text not null check (lane in ('fast', 'slow')),
        last_run_at timestamptz,
        last_success_at timestamptz,
        consecutive_failures integer not null default 0,
        next_due_at timestamptz,
        primary key (site_id, lane)
    )
    """,
    """
    create table alerts (
        id bigint generated always as identity primary key,
        site_id text not null,
        kind text not null check (kind in ('no_data', 'failed_runs')),
        source text,
        message text not null,
        raised_at timestamptz not null default now(),
        resolved_at timestamptz
    )
    """,
    """
    create unique index alerts_open on alerts (site_id, kind, coalesce(source, ''))
        where resolved_at is null
    """,
]

TABLES = [
    "alerts",
    "site_work",
    "pipeline_runs",
    "llm_text_cache",
    "recommendations",
    "recommendation_runs",
    "agents",
    "journey_steps",
    "page_stats",
    "session_events",
    "open_sessions",
    "sessions",
    "events",
    "ip_list_snapshots",
    "verdicts",
    "import_rejects",
    "import_files",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("drop function if exists drop_events_partitions_older_than(integer)")
    op.execute("drop function if exists ensure_events_partition(date)")
    for table in TABLES:
        op.execute(f"drop table if exists {table} cascade")
