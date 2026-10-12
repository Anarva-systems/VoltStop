import asyncio
import os
from pathlib import Path

import asyncpg
import httpx
import pytest
from redis.asyncio import Redis


def _load_integration_env() -> None:
    env_file = Path(__file__).parents[4] / ".env.integration.local"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        key, value = item.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_integration_env()


def _enabled(name: str) -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS") == "1" and bool(os.getenv(name))


@pytest.mark.skipif(not _enabled("SUPABASE_DB_URL"), reason="Set RUN_INTEGRATION_TESTS=1 and SUPABASE_DB_URL")
def test_supabase_postgres_connection_and_dispute_schema():
    async def run():
        connection = await asyncpg.connect(os.environ["SUPABASE_DB_URL"])
        try:
            row = await connection.fetchrow("select current_database() as database_name, current_user as role")
            assert row["database_name"] and row["role"]
            columns = await connection.fetch(
                """select table_name,column_name from information_schema.columns
                   where table_schema='public' and table_name in ('disputes','dispute_events')"""
            )
            found = {(row["table_name"], row["column_name"]) for row in columns}
            assert ("disputes", "customer_id") in found
            assert ("disputes", "resolved_by") in found
            assert ("dispute_events", "actor_type") in found
        finally:
            await connection.close()
    asyncio.run(run())


@pytest.mark.skipif(not _enabled("REDIS_URL"), reason="Set RUN_INTEGRATION_TESTS=1 and REDIS_URL")
def test_redis_connection():
    async def run():
        redis = Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=2, socket_timeout=2)
        try:
            assert await redis.ping()
        finally:
            await redis.aclose()
    asyncio.run(run())


@pytest.mark.skipif(not (_enabled("RAZORPAY_KEY_ID") and _enabled("RAZORPAY_KEY_SECRET")),
                    reason="Set RUN_INTEGRATION_TESTS=1 and Razorpay test credentials")
def test_razorpay_test_credentials_are_valid():
    key_id = os.environ["RAZORPAY_KEY_ID"]
    if not key_id.startswith("rzp_test_"):
        pytest.skip("This read-only integration test accepts test-mode Razorpay keys only")
    response = httpx.get("https://api.razorpay.com/v1/payments?count=1", auth=(key_id, os.environ["RAZORPAY_KEY_SECRET"]), timeout=10)
    assert response.status_code == 200, f"Razorpay test API returned HTTP {response.status_code}"
