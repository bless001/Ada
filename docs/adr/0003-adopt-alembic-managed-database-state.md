# ADR 0003: Adopt Alembic-Managed Database State

## Status

Accepted

## Context

The current repository creates application-owned database tables through two mechanisms: SQLAlchemy `Base.metadata.create_all()` during planning-core startup and direct SQL files under `infra/postgres/init`. The README requires durable, inspectable migrations and recovery after restarts.

## Decision

Move application-owned database schema changes to Alembic migrations. Keep compatibility startup behavior only long enough to migrate development environments safely.

## Consequences

- Clean database setup becomes reproducible.
- Schema drift becomes easier to review.
- Existing init SQL must be translated carefully to avoid breaking webhook intake.
- Startup should eventually fail clearly when migrations are missing rather than silently mutating schema.
