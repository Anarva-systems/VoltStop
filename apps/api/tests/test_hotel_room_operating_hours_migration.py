from pathlib import Path


def _migration_text() -> str:
    api_root = Path(__file__).resolve().parents[1]
    repo_root = api_root.parents[1]
    return (repo_root / "supabase/migrations/202610210001_hotel_room_operating_hours.sql").read_text(encoding="utf-8").lower()


def test_hotel_room_operating_hours_migration_is_additive():
    migration = _migration_text()
    assert "add column if not exists is_open_24_hours boolean not null default true" in migration
    assert "add column if not exists operating_start_time time not null default '00:00'" in migration
    assert "add column if not exists operating_end_time time not null default '23:59'" in migration
    assert "drop constraint if exists hotel_room_types_operating_hours_check" in migration
    assert "check (is_open_24_hours or operating_start_time <> operating_end_time)" in migration
    for destructive in ("drop table", "delete from", "truncate", "drop column"):
        assert destructive not in migration
