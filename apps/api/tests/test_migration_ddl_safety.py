from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def _text(name: str) -> str:
    return (MIGRATIONS / name).read_text(encoding="utf-8")


def _returns_columns(sql: str, signature: str) -> list[str]:
    """Read the output column names of a RETURNS TABLE function definition."""
    start = sql.index(signature)
    block = sql[start:]
    head = block.index("returns table (")
    tail = block.index("\n)", head)
    body = block[head + len("returns table ("):tail]
    return [line.strip().split()[0] for line in body.splitlines() if line.strip()]


def test_replaced_corridor_function_drops_both_signatures_first():
    """42P13 cannot be survived by CREATE OR REPLACE once the column list changes."""
    migration = _text("202610290001_charger_specs_and_route_physics.sql")
    drop_old = "drop function if exists public.route_pitstops(jsonb, double precision);"
    drop_new = "drop function if exists public.route_pitstops(jsonb, double precision, text[]);"
    assert drop_old in migration
    assert drop_new in migration
    assert migration.index(drop_old) < migration.index(drop_new)
    assert migration.index(drop_new) < migration.index("create or replace function public.route_pitstops(")


def test_corridor_function_keeps_the_privileges_of_the_version_it_replaces():
    migration = _text("202610290001_charger_specs_and_route_physics.sql")
    create_at = migration.index("create or replace function public.route_pitstops(")
    body = migration[create_at:]
    assert "security invoker" in body
    assert "revoke all on function public.route_pitstops(jsonb, double precision, text[]) from public;" in body
    assert "revoke all on function public.route_pitstops(jsonb, double precision, text[]) from anon;" in body
    assert "grant execute on function public.route_pitstops(jsonb, double precision, text[]) to authenticated;" in body


def test_nearby_vendors_replacement_keeps_its_return_contract():
    original = _text("202610020001_initial_schema.sql")
    replacement = _text("202610290001_charger_specs_and_route_physics.sql")
    signature = "create or replace function public.nearby_vendors("
    assert _returns_columns(replacement, signature) == _returns_columns(original, signature)


def test_slot_window_exclusion_names_btree_gist_opclasses_explicitly():
    """An unqualified uuid/text equality class only resolves when search_path has
    'extensions', which the migration runner is not guaranteed to provide."""
    migration = _text("202610290002_charging_slot_window_exclusion.sql")
    assert "create extension if not exists btree_gist with schema extensions;" in migration
    assert "vendor_id extensions.uuid_ops with =" in migration
    assert "service_type extensions.text_ops with =" in migration
    assert "with &&" in migration


def test_publication_changes_are_idempotent_per_table():
    """ALTER PUBLICATION ADD TABLE errors on a table that is already published, so every
    add has to check pg_publication_tables first."""
    migration = _text("202610290004_push_delivery_and_realtime.sql")
    guard = migration.index("pg_catalog.pg_publication_tables")
    add = migration.index("alter publication supabase_realtime add table")
    assert guard < add
    assert "to_regclass" in migration
    for table in ("'notifications'", "'hotel_reservations'", "'restaurant_orders'"):
        assert table in migration


def test_payout_migration_addits_only_and_replaces_no_function_contracts():
    migration = _text("202610290003_vendor_payout_routing.sql")
    assert "create or replace function public.vendor_payout_destination(vendor_id uuid)" in migration
    assert "revoke all on function public.vendor_payout_destination(uuid) from public;" in migration
    assert "grant execute on function public.vendor_payout_destination(uuid) to service_role;" in migration
    for destructive in ("drop table", "drop column", "delete from", "truncate"):
        assert destructive not in migration
