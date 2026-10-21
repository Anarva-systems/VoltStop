from pathlib import Path


def _migration_text() -> str:
    api_root = Path(__file__).resolve().parents[1]
    repo_root = api_root.parents[1]
    return (repo_root / "supabase/migrations/202610210003_charging_booking_reliability.sql").read_text(encoding="utf-8").lower()


def test_charging_booking_reliability_migration_is_additive():
    migration = _migration_text()
    assert "add column if not exists hold_expires_at timestamptz" in migration
    assert "add column if not exists idempotency_key text" in migration
    assert "add column if not exists request_fingerprint text" in migration
    assert "add constraint bookings_idempotency_unique unique (user_id, idempotency_key)" in migration
    assert "on public.bookings(hold_expires_at) where status='pending'" in migration
    assert "add column if not exists order_state text not null default 'ready'" in migration
    assert "order_state in ('creating','ready','reconciliation_required')" in migration
    for destructive in ("drop table", "delete from", "truncate", "drop column"):
        assert destructive not in migration
