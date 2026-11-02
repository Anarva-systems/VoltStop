import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest

from .db_gate import integration_database

ORDER_ID = "order_VoltStopVerify0001"

_can_run, _skip_reason = integration_database()


def _values(vendor_id, **overrides):
    row = {
        "vendor_id": vendor_id,
        "source_kind": "charging_booking",
        "source_reference_id": uuid4(),
        "razorpay_order_id": ORDER_ID,
        "gross_amount_inr": Decimal("350.00"),
        "vendor_amount_inr": Decimal("332.50"),
        "commission_inr": Decimal("17.50"),
        "rate_bps": 500,
        "status": "planned",
        "failure_reason": None,
    }
    row.update(overrides)
    return row


async def _attempt(connection, row):
    """Insert one ledger row inside a rolled-back transaction and name the outcome."""
    transaction = connection.transaction()
    await transaction.start()
    try:
        await connection.execute(
            """insert into public.vendor_payout_transfers
                 (vendor_id, source_kind, source_reference_id, razorpay_order_id,
                  gross_amount_inr, vendor_amount_inr, commission_inr, rate_bps, status, failure_reason)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            row["vendor_id"], row["source_kind"], row["source_reference_id"], row["razorpay_order_id"],
            row["gross_amount_inr"], row["vendor_amount_inr"], row["commission_inr"],
            row["rate_bps"], row["status"], row["failure_reason"],
        )
        return "accepted"
    except asyncpg.PostgresError as error:
        return type(error).__name__
    finally:
        if connection.is_in_transaction():
            await transaction.rollback()


@pytest.mark.skipif(not _can_run, reason=_skip_reason)
def test_payout_ledger_constraints_hold_on_postgres():
    """The money invariants are enforced by the database, not only by the Python planner.

    A transfer that does not account for every rupee, pays the vendor the whole order,
    or claims to be failed without a reason must be impossible to record.
    """
    async def run():
        pool = await asyncpg.create_pool(os.environ["SUPABASE_DB_URL"], min_size=1, max_size=2)
        try:
            async with pool.acquire() as connection:
                installed = await connection.fetchval("select to_regclass('public.vendor_payout_transfers') is not null")
                assert installed, "vendor payout migration has not been applied"
                gated = await connection.fetchval(
                    """select not has_table_privilege('anon','public.vendor_payout_transfers','select')
                         and not has_table_privilege('authenticated','public.vendor_payout_transfers','select')"""
                )
                assert gated, "a client role can read the vendor payout ledger"
                vendor_id = await connection.fetchval("select id from public.vendors order by id limit 1")
            if vendor_id is None:
                pytest.skip("No vendor row available to attach a payout to")

            async with pool.acquire() as connection:
                assert await _attempt(connection, _values(vendor_id)) == "accepted"
                partial = _values(vendor_id, commission_inr=Decimal("17.00"))
                assert await _attempt(connection, partial) == "CheckViolationError", \
                    "a split that loses money was accepted"
                nothing_left = _values(vendor_id, vendor_amount_inr=Decimal("350.00"), commission_inr=Decimal("0.00"))
                assert await _attempt(connection, nothing_left) == "CheckViolationError", \
                    "the platform retention floor is not enforced by the database"
                silent_failure = _values(vendor_id, status="failed", failure_reason=None)
                assert await _attempt(connection, silent_failure) == "CheckViolationError", \
                    "a failed transfer without a reason was accepted"
                thin_rate = _values(vendor_id, rate_bps=15000)
                assert await _attempt(connection, thin_rate) == "CheckViolationError", \
                    "an out-of-range commission rate was accepted"

                transaction = connection.transaction()
                await transaction.start()
                try:
                    await connection.execute(
                        """insert into public.vendor_payout_transfers
                             (vendor_id, source_kind, source_reference_id, razorpay_order_id,
                              gross_amount_inr, vendor_amount_inr, commission_inr, rate_bps)
                           values ($1,'charging_booking',$2,$3,$4,$5,$6,$7)""",
                        vendor_id, uuid4(), ORDER_ID, Decimal("350.00"), Decimal("332.50"),
                        Decimal("17.50"), 500,
                    )
                    duplicate = None
                    try:
                        await connection.execute(
                            """insert into public.vendor_payout_transfers
                                 (vendor_id, source_kind, source_reference_id, razorpay_order_id,
                                  gross_amount_inr, vendor_amount_inr, commission_inr, rate_bps)
                               values ($1,'charging_booking',$2,$3,$4,$5,$6,$7)""",
                            vendor_id, uuid4(), ORDER_ID, Decimal("350.00"), Decimal("332.50"),
                            Decimal("17.50"), 500,
                        )
                    except asyncpg.PostgresError as error:
                        duplicate = type(error).__name__
                    assert duplicate == "UniqueViolationError", \
                        "replaying the same order transfer created a second ledger row"
                finally:
                    if connection.is_in_transaction():
                        await transaction.rollback()
        finally:
            await pool.close()

    asyncio.run(run())


@pytest.mark.skipif(not _can_run, reason=_skip_reason)
def test_masked_kyc_columns_refuse_raw_document_numbers():
    """An operator must not be able to store a full PAN or bank account by mistake."""
    async def run():
        pool = await asyncpg.create_pool(os.environ["SUPABASE_DB_URL"], min_size=1, max_size=2)
        try:
            async with pool.acquire() as connection:
                target = await connection.fetchrow(
                    """select o.vendor_id from public.vendor_onboarding o
                       order by o.vendor_id limit 1"""
                )
                if target is None:
                    pytest.skip("No vendor application row to write KYC against")
                for column, raw_value, masked_value in (
                    ("kyc_pan_masked", "ABCDE1234F", "ABCDE****F"),
                    ("bank_account_masked", "1234567890123", "*****1111"),
                ):
                    transaction = connection.transaction()
                    await transaction.start()
                    try:
                        await connection.execute(
                            f"update public.vendor_onboarding set {column} = $2 where vendor_id = $1",
                            target["vendor_id"], raw_value,
                        )
                        pytest.fail(f"{column} accepted an unmasked value")
                    except asyncpg.CheckViolationError:
                        pass
                    finally:
                        if connection.is_in_transaction():
                            await transaction.rollback()
                    transaction = connection.transaction()
                    await transaction.start()
                    try:
                        await connection.execute(
                            f"update public.vendor_onboarding set {column} = $2 where vendor_id = $1",
                            target["vendor_id"], masked_value,
                        )
                    except asyncpg.CheckViolationError:
                        pytest.fail(f"{column} rejected a correctly masked value")
                    finally:
                        if connection.is_in_transaction():
                            await transaction.rollback()

                # Routing must not be switchable for a vendor whose review is incomplete.
                incomplete = await connection.fetchval(
                    """select count(*) from public.vendor_onboarding
                       where kyc_status = 'verified'
                         and (kyc_verified_at is null or kyc_verified_by is null)"""
                )
                assert incomplete == 0, "a verified KYC row is missing its verifier stamp"
        finally:
            await pool.close()

    asyncio.run(run())
