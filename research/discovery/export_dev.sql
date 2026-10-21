-- export_dev.sql - the exact, read-only recipe behind research/discovery/data/dev/.
--
-- PRED-001 DEV partition only: every statement filters events.event_date <
-- 2025-01-01 IN SQL, so no sealed fight (H1, RESERVE) is ever returned. The
-- Python loader then re-checks every row with pred_protocol.dev_only(), which
-- raises on a sealed date, and recomputes the manifest's DEV fingerprints.
--
-- Run 2026-10-21 through the read-only database connector (one SELECT each,
-- output written as CSV with the header shown in data/dev/DATA_MANIFEST.json).
-- No write, no migration, no production change.
--
-- Corners are assigned by fighter_id, never by the odds row's side label
-- (same rule as holdout_manifest.sql). BFO consensus: one opener and one
-- closer per fighter per fight in DEV (13,906 of each, checked 2026-10-21).
-- fighters: ONLY the profile columns PRED-001 section 3 allows with a caveat
-- (height, reach, stance, dob) plus sex. Career totals are never exported.

-- 0. Verification, before export: must equal holdout_manifest.json DEV
--    (decided_priced 6824, events_priced 623, the two sha256 below).
with bfo as (select id from public.odds_books where name ilike 'BFO%'),
c as (
  select o.fight_id,
         max(case when o.fighter_id = f.fighter_a_id then o.american_odds end) as a,
         max(case when o.fighter_id = f.fighter_b_id then o.american_odds end) as b
    from public.fight_odds o join public.fights f on f.id = o.fight_id
    join public.events e on e.id = f.event_id
   where o.book_id in (select id from bfo) and o.is_closer and e.event_date < date '2025-01-01'
   group by 1),
el as (
  select f.id, f.event_id, (f.winner_id = f.fighter_a_id)::int as ya
    from public.fights f join public.events e on e.id = f.event_id join c on c.fight_id = f.id
   where f.fighter_a_id is not null and f.fighter_b_id is not null
     and f.winner_id in (f.fighter_a_id, f.fighter_b_id)
     and f.is_active is distinct from false
     and e.event_date < date '2025-01-01'
     and c.a is not null and c.b is not null)
select count(*) fights, count(distinct event_id) events,
  encode(sha256(convert_to(string_agg(id::text, ',' order by id), 'UTF8')), 'hex') ids_sha256,
  encode(sha256(convert_to(string_agg(id::text || ':' || ya::text, ',' order by id), 'UTF8')), 'hex') outcomes_sha256
from el;
-- Got 2026-10-21: 6824, 623,
--   25b2e735595274bd3089b9968ed79fb9899215247cbed7bd6f8b8b7148fcbff7
--   f1b1141dd03578b3aee895b2c4d7276da0b6aa2a01e49a2c4e4e8bb41b728e5d  (match)

-- 1. fights.csv: every DEV fight (7,974), decided or not, priced or not.
--    History needs unpriced and undecided fights too.
with bfo as (select id from odds_books where name ilike 'BFO%'),
o as (select o.fight_id,
  max(case when o.fighter_id=f.fighter_a_id and o.is_opener then o.american_odds end) oa,
  max(case when o.fighter_id=f.fighter_b_id and o.is_opener then o.american_odds end) ob,
  max(case when o.fighter_id=f.fighter_a_id and o.is_closer then o.american_odds end) ca,
  max(case when o.fighter_id=f.fighter_b_id and o.is_closer then o.american_odds end) cb
  from fight_odds o join fights f on f.id=o.fight_id join events e on e.id=f.event_id
  where o.book_id in (select id from bfo) and e.event_date < date '2025-01-01' group by 1)
select f.id, f.event_id, e.event_date, f.fighter_a_id, f.fighter_b_id,
  case when f.winner_id=f.fighter_a_id then 'a' when f.winner_id=f.fighter_b_id then 'b' else '' end,
  f.method, f.end_round, f.end_time, f.scheduled_rounds, f.weight_class, f.is_title_fight::int,
  f.is_main_event::int, f.bout_order,
  a_kd, b_kd, a_sig_str_landed, b_sig_str_landed, a_sig_str_attempted, b_sig_str_attempted,
  a_td_landed, b_td_landed, a_td_attempted, b_td_attempted, a_sub_attempts, b_sub_attempts,
  a_rev, b_rev, a_ctrl_seconds, b_ctrl_seconds, a_head_landed, b_head_landed,
  a_body_landed, b_body_landed, a_leg_landed, b_leg_landed, a_distance_landed, b_distance_landed,
  a_clinch_landed, b_clinch_landed, a_ground_landed, b_ground_landed,
  o.oa, o.ob, o.ca, o.cb, f.is_active::int
from fights f join events e on e.id=f.event_id left join o on o.fight_id=f.id
where e.event_date < date '2025-01-01'
order by e.event_date, f.id;
-- (commas inside method / weight_class were replaced with ';' at export)

-- 2. fighters.csv: profile values for the 2,550 fighters who appear in DEV.
with ids as (
  select fighter_a_id id from fights f join events e on e.id=f.event_id where e.event_date < date '2025-01-01'
  union
  select fighter_b_id from fights f join events e on e.id=f.event_id where e.event_date < date '2025-01-01')
select x.id, x.height_in, x.reach_in, x.stance, x.dob, x.sex
from fighters x where x.id in (select id from ids)
order by x.id;
