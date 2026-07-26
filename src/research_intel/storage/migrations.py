"""Minimal migration support.

The MVP uses ``Base.metadata.create_all`` (idempotent) plus a schema-version
marker so future releases can add real migrations without breaking existing
local databases. When the platform outgrows SQLite, switch to Alembic and
seed it from ``SCHEMA_VERSION``.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, text

from research_intel.storage.models import Base

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def migrate(engine: Engine) -> int:
    """Create all tables and stamp the schema version. Returns current version."""
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        )
        row = conn.execute(text("SELECT version FROM schema_version")).fetchone()
        if row is None:
            conn.execute(
                text("INSERT INTO schema_version (version) VALUES (:v)"), {"v": SCHEMA_VERSION}
            )
            current = SCHEMA_VERSION
        else:
            current = int(row[0])
            if current < SCHEMA_VERSION:
                # Future migrations run here, stepwise.
                conn.execute(
                    text("UPDATE schema_version SET version = :v"), {"v": SCHEMA_VERSION}
                )
                current = SCHEMA_VERSION
    logger.debug("database schema at version %s", current)
    return current
