-- Dead-booking cleanup: UFC Fight Night: Song vs. Figueiredo (event 113, 2026-05-30)
-- ufcstats reassigned three bouts' fight ids; the scraper inserted fresh rows and
-- the stale bookings survived. Stats/rounds live on the NEW rows; the odds capture
-- (and any pre-event picks) reference the OLD rows. Repoint children, then delete.
--
-- Run in the Supabase SQL Editor. Found by the cfl_engine PIT audit 2026-07-16.
-- The engine's exporter already merges these at export time (dead-booking dedupe in
-- cfl_engine/export_data.py), so this cleanup is about DB hygiene, not model input.
--
-- stale -> canonical:
--   43   -> 27872   (Carlston Harris vs Jake Matthews; corners swapped on new row)
--   46   -> 27877   (Rei Tsuruya vs Luis Gurule)
--   8780 -> 27879   (Zhu Kangjie vs Rodrigo Vera)

begin;

with mapping(stale_id, canonical_id) as (
  values (43::bigint, 27872::bigint), (46, 27877), (8780, 27879)
)
update fight_odds fo
set fight_id = m.canonical_id
from mapping m
where fo.fight_id = m.stale_id;

with mapping(stale_id, canonical_id) as (
  values (43::bigint, 27872::bigint), (46, 27877), (8780, 27879)
)
update predictions p
set fight_id = m.canonical_id
from mapping m
where p.fight_id = m.stale_id;

with mapping(stale_id, canonical_id) as (
  values (43::bigint, 27872::bigint), (46, 27877), (8780, 27879)
)
update model_predictions mp
set fight_id = m.canonical_id
from mapping m
where mp.fight_id = m.stale_id;

with mapping(stale_id, canonical_id) as (
  values (43::bigint, 27872::bigint), (46, 27877), (8780, 27879)
)
update prediction_indicators pi
set fight_id = m.canonical_id
from mapping m
where pi.fight_id = m.stale_id;

with mapping(stale_id, canonical_id) as (
  values (43::bigint, 27872::bigint), (46, 27877), (8780, 27879)
)
update user_bets ub
set fight_id = m.canonical_id
from mapping m
where ub.fight_id = m.stale_id;

-- consensus snapshot has fight_id as PK: drop stale row if canonical already exists
delete from fight_odds_consensus_snapshot
where fight_id in (43, 46, 8780)
  and exists (select 1 from fight_odds_consensus_snapshot c2
              where c2.fight_id in (27872, 27877, 27879));

delete from fight_rounds where fight_id in (43, 46, 8780);
delete from fights where id in (43, 46, 8780);

commit;

-- Verify: all three should return the canonical row only.
-- select id, fighter_a_name, fighter_b_name from fights
-- where id in (43, 46, 8780, 27872, 27877, 27879);
