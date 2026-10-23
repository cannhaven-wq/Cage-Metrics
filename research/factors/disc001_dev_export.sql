-- disc001_dev_export.sql — the DEV export behind research/experiments/DISC-001/.
--
-- Read-only. Development data only: every row is filtered to
-- event_date < 2025-01-01 here, at the source, and the experiment's loader
-- re-checks every row with pred_protocol.dev_only(), which raises on a sealed
-- date. Nothing on or after 2025-01-01 leaves the database through this file.
--
-- It lives outside research/experiments/ because experiment code may not name
-- a database route (tests/test_prediction_protocol.py::ExperimentCode).
--
-- Benchmark: BFO closing consensus, one closer per fighter per fight, corners
-- by fighter_id, exactly as research/protocol/holdout_manifest.sql.
--
-- Output 1 -> data/dev_fights.csv, one line per fight, ordered by
-- (event_date, event_id, id):
--   id,event_id,event_date,a,b,res,method,end_round,end_secs,sched_rounds,
--   title,main,a_kd,b_kd,bfo_a,bfo_b
-- res: A | B (winner corner), D (draw), N (no contest / overturned / no winner)
-- method: K KO/TKO, T doctor's stoppage, S submission, U/P/M decision
--   unanimous/split/majority, O overturned, C could not continue, Q DQ, X other

with bfo as (select id from public.odds_books where name ilike 'BFO%'),
c as (
  select o.fight_id,
         max(case when o.fighter_id = f.fighter_a_id then o.american_odds end) as a,
         max(case when o.fighter_id = f.fighter_b_id then o.american_odds end) as b
    from public.fight_odds o
    join public.fights f on f.id = o.fight_id
    join public.events e on e.id = f.event_id
   where o.book_id in (select id from bfo) and o.is_closer
     and e.event_date < date '2025-01-01'
   group by 1),
x as (
  select f.id, f.event_id, e.event_date, f.fighter_a_id a, f.fighter_b_id b,
         case when f.winner_id = f.fighter_a_id then 'A'
              when f.winner_id = f.fighter_b_id then 'B'
              when f.method ilike 'decision%' then 'D'
              else 'N' end as res,
         case f.method when 'KO/TKO' then 'K' when 'TKO - Doctor''s Stoppage' then 'T'
              when 'Submission' then 'S' when 'Decision - Unanimous' then 'U'
              when 'Decision - Split' then 'P' when 'Decision - Majority' then 'M'
              when 'Overturned' then 'O' when 'Could Not Continue' then 'C'
              when 'DQ' then 'Q' else 'X' end as method,
         f.end_round,
         case when f.end_time ~ '^\d+:\d{2}$'
              then split_part(f.end_time, ':', 1)::int * 60 + split_part(f.end_time, ':', 2)::int end as end_secs,
         f.scheduled_rounds, f.is_title_fight::int title, f.is_main_event::int main,
         f.a_kd, f.b_kd, c.a bfo_a, c.b bfo_b
    from public.fights f
    join public.events e on e.id = f.event_id
    left join c on c.fight_id = f.id
   where e.event_date < date '2025-01-01'
     and f.fighter_a_id is not null and f.fighter_b_id is not null
     and f.is_active is distinct from false)
select string_agg(concat_ws(',', id, event_id, event_date, a, b, res, method,
                            coalesce(end_round::text, ''), coalesce(end_secs::text, ''),
                            coalesce(scheduled_rounds::text, ''), coalesce(title::text, ''),
                            coalesce(main::text, ''), coalesce(a_kd::text, ''), coalesce(b_kd::text, ''),
                            coalesce(bfo_a::text, ''), coalesce(bfo_b::text, '')),
                  E'\n' order by event_date, event_id, id) as csv
  from x;

-- Output 2 -> data/dev_fighters.csv: id,dob for every fighter in Output 1.
select string_agg(concat_ws(',', id, coalesce(dob::text, '')), E'\n' order by id) as csv
  from public.fighters
 where id in (select f.fighter_a_id from public.fights f join public.events e on e.id = f.event_id
               where e.event_date < date '2025-01-01'
              union
              select f.fighter_b_id from public.fights f join public.events e on e.id = f.event_id
               where e.event_date < date '2025-01-01');
