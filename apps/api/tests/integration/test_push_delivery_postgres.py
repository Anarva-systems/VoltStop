import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

from .db_gate import integration_database

TOKEN_A = "fcm-device-token-aaaa:0001"
TOKEN_B = "fcm-device-token-bbbb:0002"

_can_run, _skip_reason = integration_database()


@pytest.mark.skipif(not _can_run, reason=_skip_reason)
def test_notification_wakes_realtime_and_queues_exactly_one_push():
    """A second device must not turn one notification into two deliveries or two sends.

    Everything here is written inside rolled-back transactions, so the check leaves no
    notifications, tokens or queue rows behind.
    """
    async def run():
        pool = await asyncpg.create_pool(os.environ["SUPABASE_DB_URL"], min_size=2, max_size=3)
        try:
            async with pool.acquire() as connection:
                queued_by_trigger = await connection.fetchval(
                    """select exists (
                         select 1 from information_schema.triggers
                         where event_object_schema='public' and event_object_table='notifications'
                           and action_statement like '%enqueue_push_delivery%'
                       )"""
                )
                assert queued_by_trigger, "notifications do not enqueue push deliveries"
                streaming = await connection.fetchval(
                    """select count(*) from pg_catalog.pg_publication_tables
                       where pubname='supabase_realtime' and schemaname='public'
                         and tablename='notifications'"""
                )
                assert streaming == 1, "notifications are not published to realtime"
                owner = await connection.fetchval("select id from public.profiles order by id limit 1")
                if owner is None:
                    pytest.skip("No profile to own a notification")

            async with pool.acquire() as first, pool.acquire() as second:
                writer = first.transaction()
                await writer.start()
                try:
                    notification_id = await first.fetchval(
                        """insert into public.notifications(user_id,type,title,message,source_key)
                           values ($1,'integration_probe','Push probe','Row written by the integration test',$2)
                           returning id""",
                        owner, f"push-probe:{uuid4()}",
                    )
                    await first.execute(
                        """insert into public.user_push_tokens(user_id, provider, token, platform) values
                             ($1,'fcm',$2,'android'), ($1,'fcm',$3,'ios')
                           on conflict (provider, token) do nothing""",
                        owner, TOKEN_A, TOKEN_B,
                    )
                    queued = await first.fetchval(
                        "select count(*) from public.push_deliveries where notification_id = $1",
                        notification_id,
                    )
                    assert queued == 1, "one notification produced more than one queue row"

                    # The dispatcher's claim query: one row per delivery, newest device only.
                    claimed = await first.fetch(
                        """select d.id, device.token
                           from public.push_deliveries d
                           join public.notifications n on n.id = d.notification_id
                           left join lateral (
                             select t.token from public.user_push_tokens t
                             where t.user_id = n.user_id and t.provider = 'fcm'
                             order by t.last_seen_at desc limit 1
                           ) device on true
                           where d.status in ('pending','failed') and d.available_at <= now()
                           for update of d skip locked"""
                    )
                    assert len(claimed) == len({row["id"] for row in claimed}), \
                        "the claim query multiplies deliveries when a user has two devices"

                    concurrent = await second.fetch(
                        """select d.id from public.push_deliveries d
                           where d.status in ('pending','failed')
                             and d.available_at <= now()
                           for update of d skip locked"""
                    )
                    locked = {row["id"] for row in claimed}
                    assert locked, "the claim query returned nothing to lock"
                    assert locked.isdisjoint({row["id"] for row in concurrent}), \
                        "a second drain re-claimed a delivery that was already locked"
                finally:
                    if first.is_in_transaction():
                        await writer.rollback()
        finally:
            await pool.close()

    asyncio.run(run())
