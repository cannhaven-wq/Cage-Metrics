-- MKT-002 pilot: export_quotes.sql in compact form, for the database connector.
-- The SAME rows and columns, returned as one CSV text value (header line first)
-- so the pilot can save it as a file. Times are ISO-8601 UTC. Read-only.
with fx as (
  select f.id as fight_id, f.event_id, e.event_date, f.fighter_a_id, f.fighter_b_id,
         f.is_active,
         case when s.start_basis = 'event_date_fallback'
              then (e.event_date::timestamp at time zone 'UTC')
              else s.start_at end as start_at,
         s.start_basis
    from public.fights f
    join public.events e on e.id = f.event_id
    join public.v_fight_start_best s on s.fight_id = f.id
   where e.event_date >= date '2026-10-12'
),
q as (
  select o.fight_id, o.book_id, o.retrieved_at, o.feed_version, o.is_live, o.market_status,
         max(case when o.fighter_id = fx.fighter_a_id then o.american_odds end) as am_a,
         max(case when o.fighter_id = fx.fighter_b_id then o.american_odds end) as am_b,
         count(*) as n_rows
    from public.fight_odds o
    join fx on fx.fight_id = o.fight_id
   where o.book_id in (select id from public.v_odds_books_sportsbooks)
   group by 1, 2, 3, 4, 5, 6
),
rows as (
select fx.event_id, fx.event_date, fx.fight_id, fx.is_active, fx.start_at, fx.start_basis,
       q.book_id, q.retrieved_at, q.feed_version, q.is_live, q.market_status, q.am_a, q.am_b, q.n_rows
  from q join fx on fx.fight_id = q.fight_id
)
select 'event_id,event_date,fight_id,is_active,start_at,start_basis,book_id,retrieved_at,feed_version,is_live,market_status,am_a,am_b,n_rows' || E'\n' ||
       string_agg(concat_ws(',', event_id, event_date, fight_id, is_active,
                            to_char(start_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), start_basis, book_id,
                            to_char(retrieved_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                            coalesce(feed_version, ''), coalesce(is_live::text, ''), coalesce(market_status, ''),
                            coalesce(am_a::text, ''), coalesce(am_b::text, ''), n_rows),
                  E'\n' order by fight_id, book_id, retrieved_at) as csv
  from rows;
