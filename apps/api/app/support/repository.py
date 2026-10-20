from typing import Any
from uuid import UUID

import asyncpg

from app.core.errors import ApiError


class SupportRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def _owned_vendor(self, connection: asyncpg.Connection, user_id: UUID) -> UUID | None:
        rows = await connection.fetch("select id from public.vendors where owner_id=$1 order by created_at limit 2", user_id)
        if len(rows) > 1:
            raise ApiError(409, "MULTIPLE_VENDOR_PROFILES", "This account owns more than one vendor profile")
        return rows[0]["id"] if rows else None

    async def list_user(self, user_id: UUID, limit: int, offset: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            vendor_id = await self._owned_vendor(conn, user_id)
            total = await conn.fetchval(
                "select count(*) from public.support_tickets where requester_id=$1 or ($2::uuid is not null and vendor_id=$2)",
                user_id, vendor_id,
            )
            rows = await conn.fetch(
                """select t.id,t.requester_id,t.vendor_id,t.category,t.subject,t.status,t.priority,
                          t.assigned_to,t.created_at,t.updated_at,v.name as vendor_name,
                          (select count(*) from public.support_ticket_messages m where m.ticket_id=t.id and not m.is_internal) as message_count
                   from public.support_tickets t left join public.vendors v on v.id=t.vendor_id
                   where t.requester_id=$1 or ($2::uuid is not null and t.vendor_id=$2)
                   order by t.updated_at desc limit $3 offset $4""", user_id, vendor_id, limit, offset,
            )
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    async def create(self, user_id: UUID, category: str, subject: str, message: str, key: str,
                     vendor_context: bool = False, booking_id: UUID | None = None) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                vendor_id = await self._owned_vendor(conn, user_id) if vendor_context else None
                if vendor_context and vendor_id is None:
                    raise ApiError(404, "VENDOR_NOT_FOUND", "A vendor profile is required to open a business support ticket")
                if booking_id is not None:
                    booking = await conn.fetchrow("select id,user_id,vendor_id from public.bookings where id=$1 for share", booking_id)
                    if booking is None or (vendor_context and booking["vendor_id"] != vendor_id) or (not vendor_context and booking["user_id"] != user_id):
                        raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
                replay = await conn.fetchrow(
                    "select id,requester_id,vendor_id,booking_id,category,subject from public.support_tickets where idempotency_key=$1", key,
                )
                if replay:
                    if (replay["requester_id"] != user_id or replay["vendor_id"] != vendor_id
                            or replay["booking_id"] != booking_id or replay["subject"] != subject or replay["category"] != category):
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different support ticket")
                    original = await conn.fetchrow("select body from public.support_ticket_messages where idempotency_key=$1", f"{key}:initial")
                    if not original or original["body"] != message:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different support message")
                    ticket_id = replay["id"]
                    return await self._detail(conn, ticket_id, include_internal=False)
                ticket = await conn.fetchrow(
                    """insert into public.support_tickets(requester_id,vendor_id,booking_id,category,subject,idempotency_key)
                       values($1,$2,$3,$4,$5,$6) returning id""", user_id, vendor_id, booking_id, category, subject, key,
                )
                await conn.execute(
                    """insert into public.support_ticket_messages(ticket_id,sender_user_id,sender_role,body,idempotency_key)
                       values($1,$2,$3,$4,$5)""", ticket["id"], user_id,
                    "vendor" if vendor_context else "customer", message, f"{key}:initial",
                )
                await conn.execute(
                    """insert into public.support_ticket_events(ticket_id,actor_user_id,event_type,details)
                       values($1,$2,'created',jsonb_build_object('category',$3,'scope',$4))""",
                    ticket["id"], user_id, category, "vendor" if vendor_context else "customer",
                )
                await self._notify_support_admins(conn, ticket["id"], f"support-created:{ticket['id']}", subject)
                return await self._detail(conn, ticket["id"], include_internal=False)

    async def detail_for_user(self, user_id: UUID, ticket_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            vendor_id = await self._owned_vendor(conn, user_id)
            authorized = await conn.fetchval(
                "select exists(select 1 from public.support_tickets where id=$1 and (requester_id=$2 or ($3::uuid is not null and vendor_id=$3)))",
                ticket_id, user_id, vendor_id,
            )
            return await self._detail(conn, ticket_id, False) if authorized else None

    async def detail_admin(self, ticket_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            return await self._detail(conn, ticket_id, True)

    async def _detail(self, conn: asyncpg.Connection, ticket_id: UUID, include_internal: bool) -> dict[str, Any] | None:
        ticket = await conn.fetchrow(
            f"""select t.id,t.requester_id,t.vendor_id,t.booking_id,t.category,t.subject,t.status,t.priority,t.assigned_to,
                      t.created_at,t.updated_at,p.name as requester_name,auth_user.email as requester_email,
                      v.name as vendor_name
               from public.support_tickets t join public.profiles p on p.id=t.requester_id
               left join auth.users auth_user on auth_user.id=p.id
               left join public.vendors v on v.id=t.vendor_id where t.id=$1""", ticket_id,
        )
        if not ticket:
            return None
        messages = await conn.fetch(
            """select id,sender_user_id,sender_role,body,is_internal,created_at from public.support_ticket_messages
               where ticket_id=$1 and ($2::boolean or not is_internal) order by created_at""", ticket_id, include_internal,
        )
        events = await conn.fetch(
            "select id,actor_user_id,event_type,details,created_at from public.support_ticket_events where ticket_id=$1 order by created_at",
            ticket_id,
        )
        return {**dict(ticket), "messages": [dict(row) for row in messages], "events": [dict(row) for row in events]}

    async def add_message(self, user_id: UUID, ticket_id: UUID, message: str, key: str,
                          admin: bool = False, internal: bool = False) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                vendor_id = await self._owned_vendor(conn, user_id) if not admin else None
                ticket = await conn.fetchrow("select * from public.support_tickets where id=$1 for update", ticket_id)
                if not ticket:
                    raise ApiError(404, "SUPPORT_TICKET_NOT_FOUND", "Support ticket was not found")
                if not admin and ticket["requester_id"] != user_id and (vendor_id is None or ticket["vendor_id"] != vendor_id):
                    raise ApiError(404, "SUPPORT_TICKET_NOT_FOUND", "Support ticket was not found")
                existing = await conn.fetchrow("select ticket_id,body,sender_user_id,is_internal from public.support_ticket_messages where idempotency_key=$1", key)
                if existing:
                    if (existing["ticket_id"] != ticket_id or existing["body"] != message
                            or existing["sender_user_id"] != user_id or existing["is_internal"] != internal):
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different message")
                    return await self._detail(conn, ticket_id, admin)
                if ticket["status"] in ("resolved", "closed") and not admin:
                    raise ApiError(409, "SUPPORT_TICKET_CLOSED", "A resolved ticket must be reopened by support before replying")
                sender_role = "admin" if admin else ("vendor" if ticket["vendor_id"] and vendor_id == ticket["vendor_id"] else "customer")
                await conn.execute(
                    """insert into public.support_ticket_messages(ticket_id,sender_user_id,sender_role,body,is_internal,idempotency_key)
                       values($1,$2,$3,$4,$5,$6)""", ticket_id, user_id, sender_role, message, internal, key,
                )
                if not admin:
                    await conn.execute("update public.support_tickets set status='open',updated_at=now() where id=$1", ticket_id)
                    if ticket["requester_id"] != user_id:
                        await conn.execute(
                            """insert into public.notifications(user_id,type,title,message,source_key)
                               values($1,'support_reply','Support ticket updated',$2,$3) on conflict(source_key) do nothing""",
                            ticket["requester_id"], f"A reply was added to {ticket['subject']}.", f"support-message:{key}:requester",
                        )
                    else:
                        await self._notify_support_admins(conn, ticket_id, f"support-message:{key}:admins", ticket["subject"])
                else:
                    await conn.execute(
                        "insert into public.support_ticket_events(ticket_id,actor_user_id,event_type,details) values($1,$2,$3,jsonb_build_object('internal',$4))",
                        ticket_id, user_id, "internal_note" if internal else "admin_reply", internal,
                    )
                    if not internal:
                        await conn.execute(
                            """insert into public.notifications(user_id,type,title,message,source_key)
                               values($1,'support_reply','Support replied',$2,$3) on conflict(source_key) do nothing""",
                            ticket["requester_id"], f"Support replied to {ticket['subject']}.", f"support-message:{key}:requester",
                        )
                return await self._detail(conn, ticket_id, admin)

    async def admin_list(self, status: str | None, priority: str | None, query: str | None, limit: int, offset: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            args = (status, priority, query)
            where = "($1::text is null or t.status=$1) and ($2::text is null or t.priority=$2) and ($3::text is null or t.subject ilike '%'||$3||'%' or auth_user.email ilike '%'||$3||'%' or p.name ilike '%'||$3||'%')"
            total = await conn.fetchval(
                f"select count(*) from public.support_tickets t join public.profiles p on p.id=t.requester_id left join auth.users auth_user on auth_user.id=p.id where {where}", *args,
            )
            rows = await conn.fetch(
                f"""select t.id,t.requester_id,t.vendor_id,t.booking_id,t.category,t.subject,t.status,t.priority,t.assigned_to,
                           t.created_at,t.updated_at,p.name as requester_name,auth_user.email as requester_email,v.name as vendor_name,
                           (select count(*) from public.support_ticket_messages m where m.ticket_id=t.id) as message_count
                    from public.support_tickets t join public.profiles p on p.id=t.requester_id
                    left join auth.users auth_user on auth_user.id=p.id
                    left join public.vendors v on v.id=t.vendor_id where {where}
                    order by case t.priority when 'urgent' then 0 when 'high' then 1 else 2 end,t.updated_at desc limit $4 offset $5""",
                *args, limit, offset,
            )
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    async def admin_update(self, actor_id: UUID, role: str, ticket_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        reason = values.pop("reason")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("select * from public.support_tickets where id=$1 for update", ticket_id)
                if not row:
                    raise ApiError(404, "SUPPORT_TICKET_NOT_FOUND", "Support ticket was not found")
                before = {"status": row["status"], "priority": row["priority"], "assigned_to": row["assigned_to"]}
                if "assigned_to" in values and values["assigned_to"] is not None:
                    active = await conn.fetchval("select exists(select 1 from public.admin_users where user_id=$1 and is_active)", values["assigned_to"])
                    if not active:
                        raise ApiError(422, "INVALID_SUPPORT_ASSIGNEE", "The assigned administrator is not active")
                after = {**before, **values}
                await conn.execute(
                    "update public.support_tickets set status=$2,priority=$3,assigned_to=$4,updated_at=now(),resolved_at=case when $2 in ('resolved','closed') then coalesce(resolved_at,now()) else null end where id=$1",
                    ticket_id, after["status"], after["priority"], after["assigned_to"],
                )
                event = await conn.fetchrow(
                    """insert into public.support_ticket_events(ticket_id,actor_user_id,event_type,details)
                       values($1,$2,'admin_update',jsonb_build_object('before',$3::jsonb,'after',$4::jsonb,'reason',$5)) returning id""",
                    ticket_id, actor_id, _json(before), _json(after), reason,
                )
                await conn.execute(
                    """insert into public.admin_audit_logs(admin_user_id,role_name,action,entity_type,entity_id,reason,before_state,after_state)
                       values($1,$2,'support.ticket_updated','support_ticket',$3,$4,$5::jsonb,$6::jsonb)""",
                    actor_id, role, str(ticket_id), reason, _json(before), _json(after),
                )
                await conn.execute(
                    """insert into public.notifications(user_id,type,title,message,source_key)
                       values($1,'support_status','Support request updated',$2,$3) on conflict(source_key) do nothing""",
                    row["requester_id"], f"{row['subject']} is now {after['status']}.", f"support-state:{event['id']}",
                )
        return await self.detail_admin(ticket_id) or {}

    async def _notify_support_admins(self, conn: asyncpg.Connection, ticket_id: UUID, key: str, subject: str) -> None:
        await conn.execute(
            """insert into public.notifications(user_id,type,title,message,source_key)
               select au.user_id,'support_ticket','New support request',$2,$3||':'||au.user_id::text
               from public.admin_users au join public.admin_role_permissions rp on rp.role_name=au.role_name
               where au.is_active and rp.permission_key='support:manage'
               on conflict(source_key) do nothing""", f"A support request was opened: {subject}", key,
        )


def _json(value: dict[str, Any]) -> str:
    import json
    return json.dumps({key: str(item) if isinstance(item, UUID) else item for key, item in value.items()})
