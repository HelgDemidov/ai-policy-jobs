import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# alembic/ lives at the repo root, but the schema it migrates is defined in
# web/api/_schema.py (that module's home is fixed by Vercel's Root Directory
# sandboxing — a deployed function can't reach outside web/, see _schema.py's
# own docstring). Alembic itself only ever runs locally (never inside the
# deployed function), so reaching across that boundary here is safe — same
# sys.path pattern tests/conftest.py already uses for the same reason.
WEB_API_DIR = Path(__file__).resolve().parent.parent / "web" / "api"
if str(WEB_API_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_API_DIR))

import _schema  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = _schema.metadata

# DATABASE_URL from the environment, not alembic.ini's static placeholder —
# same value _repo.py's get_engine() reads, normalized the same way (Neon
# hands out a bare postgresql:// scheme that needs rewriting to
# postgresql+psycopg://, see _schema.resolve_database_url's docstring).
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    config.set_main_option("sqlalchemy.url", _schema.resolve_database_url(_database_url).replace("%", "%%"))

# search_vector + its GIN index (migration 0002) exist in the real DB but
# not in _schema.py's portable metadata — tsvector has no SQLite
# equivalent, so it's added via raw SQL rather than a Core Column (see
# that migration's docstring). Without this exclusion, autogenerate/
# `alembic check` would perpetually propose dropping both — same footgun
# and same fix as scopus_search_code's env.py _include_object exclusion
# for its own raw-SQL-only indexes.
_MIGRATION_ONLY_OBJECTS = {("column", "search_vector"), ("index", "ix_postings_search_vector")}


def include_object(object, name, type_, reflected, compare_to):
    return (type_, name) not in _MIGRATION_ONLY_OBJECTS


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
