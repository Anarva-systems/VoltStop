"""Decide whether the Postgres-backed checks can actually run here.

An exported RUN_INTEGRATION_TESTS=1 is not proof that a database answers. Without a
handshake, a laptop with no local Supabase reports a missing service as six failing
schema checks, which is indistinguishable from a broken migration. So these tests skip
when nothing is listening, and only run — failing loudly on a wrong schema — once the
DSN is reachable. Bad credentials and an unknown database are deliberately not swallowed:
the database is configured then, so the checks run and each one reports the server's own
error instead of skipping quietly.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg

_NOT_A_SERVER = (
    OSError,  # connection refused, unreachable, or an unresolvable host
    asyncio.TimeoutError,
    asyncpg.PostgresConnectionError,  # something answered the port, but not as PostgreSQL
)

_probe: tuple[bool, str] | None = None


def load_integration_env() -> None:
    """Fill in `.env.integration.local` without overriding anything already exported."""
    env_file = Path(__file__).parents[4] / ".env.integration.local"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        key, value = item.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def integration_database() -> tuple[bool, str]:
    """Return whether the Postgres checks can run, and why not when they cannot."""
    global _probe
    load_integration_env()
    dsn = os.getenv("SUPABASE_DB_URL", "").strip()
    if os.getenv("RUN_INTEGRATION_TESTS") != "1" or not dsn:
        return False, "Set RUN_INTEGRATION_TESTS=1 and SUPABASE_DB_URL"
    if _probe is None:
        _probe = _handshake(dsn)
    return _probe


def _handshake(dsn: str) -> tuple[bool, str]:
    target = urlsplit(dsn)
    host = f"{target.hostname}:{target.port or 5432}" if target.hostname else "the configured host"
    try:
        asyncio.run(_select_one(dsn))
    except _NOT_A_SERVER as error:
        return False, f"No PostgreSQL answered at {host}: {type(error).__name__}: {error}"
    except Exception:
        pass
    return True, ""


async def _select_one(dsn: str) -> None:
    connection = await asyncpg.connect(dsn=dsn, timeout=5)
    try:
        await connection.fetchval("select 1")
    finally:
        await connection.close()
