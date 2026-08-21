-- Country of origin for fighters.
--
-- Source of truth is the "Place of Birth" field on ufc.com athlete pages,
-- with Wikidata (P27, country of citizenship) as the fallback for fighters
-- whose ufc.com page is missing or has no birthplace listed.
--
-- NOTE: this is deliberately NOT derived from events.location. Where a fight
-- happens says nothing about where a fighter is from.

ALTER TABLE fighters ADD COLUMN IF NOT EXISTS birth_place  text;  -- "Oakland, United States" as printed
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS country      text;  -- "United States"
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS country_code text;  -- ISO 3166-1 alpha-2, "US"
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS country_src  text;  -- 'ufc.com' | 'wikidata'
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS country_checked_at timestamptz;

COMMENT ON COLUMN fighters.country_checked_at IS
  'Last lookup attempt, successful or not — lets the backfill skip recent misses.';

CREATE INDEX IF NOT EXISTS fighters_country_code_idx ON fighters (country_code);
