-- Fighting style (discipline) for fighters — T-102, owner 2026-10-16.
--
-- PLAIN ENGLISH: the fighter's discipline as the UFC lists it — "Boxer",
-- "Kickboxer", "Wrestling", "Brazilian Jiu-Jitsu" — read from the "Fighting
-- style" field on their UFC.com athlete page. It replaces the calculated
-- striker / grappler / hybrid label on Fight Lab and the fighter page: that
-- label was worked out from round one of the last five fights, and it called
-- Joaquin Buckley a grappler because being held down by Brady and Usman
-- dragged his striking numbers to nothing.
--
-- Written by build/check-fighting-style.js (.github/workflows/fighting-style.yml).
-- A value a person sets carries fighting_style_src = 'manual' and is never
-- touched by the job. Nothing here is calculated, and nothing is guessed: a
-- fighter whose page has no style, or whose page was not found, stays NULL.
--
-- Additive only. `fighters` already grants table-level SELECT to anon and
-- authenticated, so the new columns are readable by the site with no new
-- grant, and nothing in the existing write path changes.
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS fighting_style text;             -- as printed on UFC.com, e.g. "Kickboxer"
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS fighting_style_src text;         -- 'ufc.com' | 'manual'
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS fighting_style_checked_at timestamptz;
COMMENT ON COLUMN fighters.fighting_style IS
  'Discipline as listed in the "Fighting style" field of the UFC.com athlete page. Not calculated.';
COMMENT ON COLUMN fighters.fighting_style_checked_at IS
  'Last UFC.com lookup, successful or not — lets the job skip recent misses.';
