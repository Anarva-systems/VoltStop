from pathlib import Path


def _migration_texts() -> tuple[str, str]:
    api_root = Path(__file__).resolve().parents[1]
    repo_root = api_root.parents[1]
    return (
        (repo_root / "supabase/migrations/202610140001_driver_upcoming_trips.sql")
        .read_text(encoding="utf-8")
        .lower(),
        (api_root / "migrations/neon/007_driver_upcoming_trips.sql")
        .read_text(encoding="utf-8")
        .lower(),
    )


def test_driver_trip_migrations_are_additive_and_keep_data_constraints():
    for migration in _migration_texts():
        assert "create table public.driver_trips" in migration
        assert "references public.profiles(id) on delete cascade" in migration
        assert "references public.driver_vehicles(id) on delete set null" in migration
        assert "references public.routes(id) on delete set null" in migration
        assert "unique (driver_id, idempotency_key)" in migration
        assert "available_seats between 1 and 8" in migration
        assert "estimated_arrival_at > departure_at" in migration
        assert "status in ('scheduled', 'in_progress', 'completed', 'cancelled')" in migration

    supabase, neon = _migration_texts()
    assert "enable row level security" in supabase
    assert "create policy driver_trips_select_own" in supabase
    assert "using (driver_id = (select auth.uid()))" in supabase
    assert "grant select on public.driver_trips to authenticated" in supabase
    assert "grant insert" not in supabase
    assert "grant update" not in supabase
    assert "grant delete" not in supabase
    assert "driver_trips_discovery_idx" in neon
