-- =============================================================================
-- Card-to-card return rate: of the browsers that looked at card N during its
-- fight week, what share came back during card N+1's fight week?
-- =============================================================================
-- Computed from the hub_visits ledger (hub_visits_migration.sql) — not from a
-- browser event. Run with the service role:
--     python cfl_engine/run_sql_mgmt.py sql/retention_return_rate.sql
-- or paste into the SQL editor.
--
-- "Fight week" for a card = the 7 days ending on its event date, plus the day
-- after (results land). Cards are ordered by event_date; N+1 is the next card
-- that has any visits at all, so a card nobody looked at does not break the
-- chain.
--
-- Output, one row per card N (that has a following card):
--   event_id, event_name, event_date, visitors (browsers during N's week),
--   next_event_id, next_event_name, returned (of those browsers, how many
--   showed up during N+1's week), return_rate_pct.
-- =============================================================================

with visited as (
  select distinct v.visitor_key, v.event_id
  from public.hub_visits v
  join public.events e on e.id = v.event_id
  where v.seen_on between e.event_date - 7 and e.event_date + 1
),
cards as (
  select e.id, e.name, e.event_date,
         lead(e.id)   over (order by e.event_date, e.id) as next_id,
         lead(e.name) over (order by e.event_date, e.id) as next_name
  from public.events e
  where e.id in (select event_id from visited)
),
cohort as (
  select c.id, c.name, c.event_date, c.next_id, c.next_name,
         count(distinct v.visitor_key) as visitors,
         count(distinct v.visitor_key) filter (
           where exists (select 1 from visited w where w.visitor_key = v.visitor_key and w.event_id = c.next_id)
         ) as returned
  from cards c
  join visited v on v.event_id = c.id
  where c.next_id is not null
  group by c.id, c.name, c.event_date, c.next_id, c.next_name
)
select id as event_id, name as event_name, event_date,
       next_id as next_event_id, next_name as next_event_name,
       visitors, returned,
       round(100.0 * returned / nullif(visitors, 0), 1) as return_rate_pct
from cohort
order by event_date desc;
