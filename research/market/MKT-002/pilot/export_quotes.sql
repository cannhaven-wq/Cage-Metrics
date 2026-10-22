-- MKT-002 pilot: the ONE read the pilot makes. Read-only. Prices and booking
-- fields only: no result, method, round, time-of-finish or statistics column,
-- and no results table, is named here (tests/test_market_research.py checks).
--
-- Scope: UFC cards dated on or after 2026-10-12 (after PRED-001's RESERVE
-- window), quotes from real sportsbooks only (v_odds_books_sportsbooks), from
-- the provenance feed (W3). One row per capture per book per fight, both
-- corners on the same row; a capture with only one corner keeps the other NULL
-- so the pilot can count one-sided quotes.
--
-- start_at follows the preregistration draft: the bout's bell or the
-- provider's commence time when known, otherwise 00:00 UTC on the event date
-- (earlier than the view's own 18:00 fallback, so never late).
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
)
select fx.event_id, fx.event_date, fx.fight_id, fx.is_active, fx.start_at, fx.start_basis,
       q.book_id, q.retrieved_at, q.feed_version, q.is_live, q.market_status, q.am_a, q.am_b, q.n_rows
  from q join fx on fx.fight_id = q.fight_id
 order by fx.fight_id, q.book_id, q.retrieved_at;
