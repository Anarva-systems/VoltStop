import asyncio
import os
from decimal import Decimal

import asyncpg
import pytest


def _enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS") == "1" and bool(os.getenv("SUPABASE_DB_URL"))


@pytest.mark.skipif(not _enabled(), reason="Set RUN_INTEGRATION_TESTS=1 and SUPABASE_DB_URL")
def test_availability_window_exclusion_is_installed_and_enforced():
    """The exclusion constraint behaves as intended on a real Postgres.

    The anchor is a slot that already exists, and every candidate insert is rolled
    back, so this verifies the constraint without leaving availability behind.
    """
    async def attempt(pool, anchor, offset_hours, length_hours):
        async with pool.acquire() as connection:
            transaction = connection.transaction()
            await transaction.start()
            try:
                await connection.execute(
                    """insert into public.charging_slots
                         (vendor_id, slot_start_time, slot_end_time, capacity, price_inr, service_type)
                       select $1, bounds.anchor_end + ($2 * interval '1 hour'),
                              bounds.anchor_end + (($2 + $3) * interval '1 hour'), $4, $5, $6
                       from (select $7::timestamptz as anchor_end) bounds""",
                    anchor["vendor_id"], offset_hours, length_hours,
                    2, Decimal("500.00"), anchor["service_type"],
                    anchor["slot_end_time"],
                )
                return "accepted"
            except asyncpg.ExclusionViolationError:
                return "rejected"
            finally:
                if transaction.is_active():
                    await transaction.rollback()

    async def run():
        pool = await asyncpg.create_pool(os.environ["SUPABASE_DB_URL"], min_size=2, max_size=3)
        try:
            async with pool.acquire() as connection:
                enforced = await connection.fetchval(
                    """select count(*) from pg_constraint c
                       join pg_namespace n on n.oid=c.connamespace
                       where n.nspname='public' and c.conname='charging_slots_no_overlapping_window'
                         and c.contype='x' and c.convalidated"""
                )
                assert enforced == 1, "exclusion constraint is missing or still unvalidated"
                anchor = await connection.fetchrow(
                    """select distinct on (vendor_id, service_type)
                              vendor_id, service_type, slot_start_time, slot_end_time
                       from public.charging_slots
                       where status <> 'closed' and slot_end_time > now()
                       order by vendor_id, service_type, slot_end_time desc
                       limit 1"""
                )
            if anchor is None:
                pytest.skip("No open availability window to collide with")
            length = (anchor["slot_end_time"] - anchor["slot_start_time"]).total_seconds() / 3600
            identical = await attempt(pool, anchor, -length, length)
            assert identical == "rejected", "an identical window for the same service was accepted"
            partial = await attempt(pool, anchor, -(length / 2), length)
            assert partial == "rejected", "a partially overlapping window was accepted"
            adjacent = await attempt(pool, anchor, 0, length)
            assert adjacent == "accepted", "a back-to-back window must not collide"
            later = await attempt(pool, anchor, 48, length)
            assert later == "accepted", "a free window far from the anchor must be insertable"
        finally:
            await pool.close()

    asyncio.run(run())


@pytest.mark.skipif(not _enabled(), reason="Set RUN_INTEGRATION_TESTS=1 and SUPABASE_DB_URL")
def test_closed_window_does_not_block_an_equivalent_replacement():
    """Closing a slot has to free its range, or vendors cannot re-publish availability."""
    async def run():
        pool = await asyncpg.create_pool(os.environ["SUPABASE_DB_URL"], min_size=1, max_size=2)
        try:
            async with pool.acquire() as connection:
                anchor = await connection.fetchrow(
                    """select distinct on (vendor_id, service_type)
                              vendor_id, service_type, slot_start_time, slot_end_time
                       from public.charging_slots
                       where status = 'closed'
                       order by vendor_id, service_type, slot_end_time desc
                       limit 1"""
                )
            if anchor is None:
                pytest.skip("No closed availability window to reuse")
            async with pool.acquire() as connection:
                transaction = connection.transaction()
                await transaction.start()
                try:
                    await connection.execute(
                        """insert into public.charging_slots
                             (vendor_id, slot_start_time, slot_end_time, capacity, price_inr, service_type)
                           values ($1,$2,$3,$4,$5,$6)""",
                        anchor["vendor_id"], anchor["slot_start_time"], anchor["slot_end_time"],
                        2, Decimal("500.00"), anchor["service_type"],
                    )
                except asyncpg.ExclusionViolationError:
                    pytest.fail("a closed slot still reserves its availability window")
                finally:
                    if transaction.is_active():
                        await transaction.rollback()
        finally:
            await pool.close()

    asyncio.run(run())
