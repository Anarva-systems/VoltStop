from pathlib import Path


def _migration_text() -> str:
    api_root = Path(__file__).resolve().parents[1]
    repo_root = api_root.parents[1]
    return (repo_root / "supabase/migrations/202610210002_refund_integrity_indexes.sql").read_text(encoding="utf-8").lower()


def test_refund_integrity_migration_is_additive_and_matches_state_machine():
    migration = _migration_text()
    assert "create unique index if not exists refunds_payment_open_idx" in migration
    assert "create unique index if not exists hotel_refunds_payment_open_idx" in migration
    assert "on public.refunds(payment_id) where status not in ('failed', 'rejected')" in migration
    assert "on public.hotel_refunds(payment_id) where status not in ('failed', 'rejected')" in migration
    for destructive in ("drop table", "delete from", "truncate", "drop column"):
        assert destructive not in migration
