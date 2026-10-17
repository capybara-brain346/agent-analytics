"""Alembic environment. Migrations are raw SQL with `op.execute` (no ORM models)."""

from alembic import context
from sqlalchemy import create_engine, pool

from src.config import get_settings


def sqlalchemy_url() -> str:
    return get_settings().database_url.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations_offline() -> None:
    context.configure(url=sqlalchemy_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(sqlalchemy_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
