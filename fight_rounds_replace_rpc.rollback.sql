-- Rollback for fight_rounds_replace_rpc.sql. Drops the two functions only; no
-- data changes. After this the scraper refuses to write rounds (it never falls
-- back to the old delete-then-insert), so roll the scraper back first if the
-- old behaviour is wanted.
DROP FUNCTION IF EXISTS public.replace_fight_rounds(bigint, jsonb);
DROP FUNCTION IF EXISTS public.replace_fight_rounds_non_ufc(bigint, jsonb);
