# Supabase database cutover

VoltStop now treats Supabase PostgreSQL as the only supported application database. Staging and production reject a `DATABASE_URL` whose host is not a Supabase database or Supabase pooler host. Keep using the existing environment variable name, but set it to the Supabase project's **Transaction pooler** connection string for Vercel (port 6543). Local development can use the local Supabase database connection.

## Fix the cancellation migration error

`202610200001_customer_cancellation_policy.sql` is now safe to re-run if some columns or indexes already exist. The earlier SQL editor run reported that `hotel_reservations.check_in_time` exists, so update the migration file from GitHub and run that complete file in **Supabase Dashboard → SQL Editor**. Do not rerun the initial schema or unrelated migrations. Verify the expected columns afterward:

```sql
select table_name, column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name in ('bookings', 'hotel_reservations')
  and column_name in (
    'check_in_time', 'check_out_time', 'cancellation_fee_inr',
    'refund_amount_inr', 'cancellation_policy_version', 'cancelled_at'
  )
order by table_name, column_name;
```

The hotel time fields should be `time without time zone`; money values should be `numeric`. The migration must also leave the hotel status check accepting `refund_partial` and create the two cancellation timestamp indexes. If the existing columns have different types, stop and inspect them before changing data.

## Move production traffic

1. In Supabase, create a database backup/export and record row counts for every application table. Keep the current Neon project untouched until the cutover is verified.
2. Confirm which database currently holds production data. If Supabase is already the source of truth, no data copy is needed; point Vercel's API `DATABASE_URL` at Supabase's transaction pooler and keep the API's `SUPABASE_URL` and public key on that same Supabase project.
3. If Neon still contains unique production rows, export only VoltStop application tables and plan an identity-aware import. `public.profiles.id`, bookings, vendors, and reservations refer to Supabase Auth user IDs; do not copy or overwrite Supabase's managed `auth` schema with a raw database dump. Reconcile every referenced user ID through Supabase Auth before importing dependent rows.
4. Apply Supabase migrations in chronological order to a fresh Supabase database, or apply only migrations not already present to the existing project. The SQL Editor does not automatically register manual SQL runs in Supabase's migration history; reconcile `supabase_migrations.schema_migrations` only through the Supabase CLI workflow and do not assume a manually run migration is recorded.
5. Deploy the API with the Supabase pooler URL. Check `/api/v1/health` and `/api/v1/ready`, then verify login, customer and vendor lookup, bookings, hotel reservations, refunds, and admin operations against the intended project.
6. Compare row counts and representative records with the backup, monitor errors, and keep Neon read-only during the rollback window. Delete the Neon project only after the owner confirms it contains no unique data and the Supabase cutover has passed verification.

No live database was changed as part of this code update. The repository no longer contains a Neon migration track; the previous Neon project is not automatically deleted by a Git change.
