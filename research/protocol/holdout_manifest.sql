-- holdout_manifest.sql — the exact recipe behind holdout_manifest.json (PRED-001).
--
-- Read-only. Re-run it at any time: the three hashes must equal the manifest.
-- A difference means the sealed data changed (a scraper correction, a booking
-- retired, a price row altered) and the auditor must report it BEFORE any look.
--
-- Benchmark source: BestFightOdds closing consensus (odds_books.name ILIKE 'BFO%'),
-- rows with is_closer, one per fighter per fight. Checked 2026-10-13: 0 of 15,362
-- fighter-sides carry more than one BFO closer, so max() below never chooses.
-- Corners are assigned by fighter_id, never by the side label (1,578 rows have a
-- side that contradicts the fighter, per the 2026-09-16 integrity audit).
--
-- Exclusions: draws and no-contests; dead bookings (is_active = false); fights
-- 43, 46 and 8780, rebooked in place (the row now holds a different matchup from
-- the one the prices were recorded on — DATA_INTEGRITY_AUDIT_2026-09-16).

with bfo as (select id from public.odds_books where name ilike 'BFO%'),
c as (
  select o.fight_id,
         max(case when o.fighter_id = f.fighter_a_id then o.american_odds end) as a,
         max(case when o.fighter_id = f.fighter_b_id then o.american_odds end) as b
    from public.fight_odds o
    join public.fights f on f.id = o.fight_id
   where o.book_id in (select id from bfo) and o.is_closer
   group by 1),
el as (
  select f.id, f.event_id, (f.winner_id = f.fighter_a_id)::int as ya, c.a, c.b
    from public.fights f
    join public.events e on e.id = f.event_id
    join c on c.fight_id = f.id
   where f.fighter_a_id is not null and f.fighter_b_id is not null
     and f.winner_id in (f.fighter_a_id, f.fighter_b_id)
     and f.is_active is distinct from false
     and e.event_date between date '2025-01-01' and date '2026-07-11'
     and c.a is not null and c.b is not null
     and f.id not in (43, 46, 8780))
select count(*)                       as fights,
       count(distinct event_id)       as events,
       encode(sha256(convert_to(string_agg(id::text, ',' order by id), 'UTF8')), 'hex')                               as ids_sha256,
       encode(sha256(convert_to(string_agg(id::text || ':' || a::text || ':' || b::text, ',' order by id), 'UTF8')), 'hex') as prices_sha256,
       encode(sha256(convert_to(string_agg(id::text || ':' || ya::text, ',' order by id), 'UTF8')), 'hex')            as outcomes_sha256,
       encode(sha256(convert_to(string_agg(id::text || ':' || event_id::text, ',' order by id), 'UTF8')), 'hex')      as events_sha256
  from el;
-- Expected (2026-10-13): 710 fights, 63 events,
--   ids      97ff805efc28921df03e91e126a4cf05c7ac539be10979fe07b597a892ee000a
--   prices   7b259a1900c36946831bfcb5bb9b94f6ae019e2ebbdf6af009ef2f2d8117fa4d
--   outcomes 14112440771f6746f4696fd808fa576a64b68623fbafefc9b7652182f3d854ff
--   events   49701a1ea9c730edc39bb4e64f6af1f9a129de3e01e02a5c7452b5aed20f5789
