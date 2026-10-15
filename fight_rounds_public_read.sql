-- fight_rounds_public_read.sql — records an existing grant; nothing to apply.
--
-- Fight Lab's research workspace (fight.html, "Last 5" rates) reads
-- public.fight_rounds from the browser. Production already holds this grant
-- and an RLS SELECT policy for both browser roles — checked 2026-10-15 via
-- information_schema.role_table_grants and pg_policies. It lived only in
-- production, and tests/t088-least-privilege.test.js requires every object a
-- page reads to be granted in repo SQL, because once T-088's default-private
-- rule lands an ungranted read returns "permission denied".
--
-- Read only. Round data is public UFCStats data, the same rows the per-round
-- views are built from. Idempotent: re-granting an existing privilege is a
-- no-op and raises no NOTICE.

GRANT SELECT ON TABLE public.fight_rounds TO anon, authenticated;
