-- MKT-002 pilot, read 1 of 2: quality and coverage, aggregates only.
-- Read-only. Prices and booking fields only: no result, method, round,
-- finish-time or statistics column and no results table is named here
-- (tests/test_market_research.py). Scope: UFC cards dated on or after
-- 2026-10-12, quotes from real sportsbooks (v_odds_books_sportsbooks), one row
-- per capture per book per bout with both corners side by side. start_at is the
-- bout's bell or the provider's commence time, else 00:00 UTC on the event date
-- (earlier than the view's own 18:00 fallback, so never late). A quote is
-- graded by the FIRST quality rule it fails.
with fx as (
  select f.id as fight_id, f.event_id, e.event_date, f.fighter_a_id, f.fighter_b_id, f.is_active,
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
         max(case when o.fighter_id = fx.fighter_b_id then o.american_odds end) as am_b
    from public.fight_odds o
    join fx on fx.fight_id = o.fight_id
   where o.book_id in (select id from public.v_odds_books_sportsbooks)
   group by 1, 2, 3, 4, 5, 6
),
graded as (
  select q.*, fx.event_id, fx.event_date, fx.start_at, fx.start_basis,
         case when fx.is_active is false then 'fight_not_active'
              when q.feed_version is null or q.feed_version not like 'odds-api-v4%' then 'not_w3_feed'
              when q.retrieved_at is null then 'no_retrieved_at'
              when q.is_live then 'live'
              when coalesce(q.market_status, 'open') <> 'open' then 'status_' || q.market_status
              when q.am_a is null or q.am_b is null then 'one_sided'
              when abs(q.am_a) not between 100 and 10000 or abs(q.am_b) not between 100 and 10000 then 'beyond_100_to_1'
              when q.retrieved_at >= fx.start_at then 'after_start'
              else 'kept' end as grade
    from q join fx on fx.fight_id = q.fight_id
),
kept as (select * from graded where grade = 'kept'),
gaps as (
  select extract(epoch from (retrieved_at - lag(retrieved_at) over (partition by fight_id, book_id order by retrieved_at))) / 60 as gap_min
    from kept where retrieved_at >= start_at - interval '24 hours'
)
select json_build_object(
  'rows', (select count(*) from graded),
  'fights_any_quote', (select count(distinct fight_id) from graded),
  'fights_kept_quote', (select count(distinct fight_id) from kept),
  'grades', (select json_object_agg(grade, n) from (select grade, count(*) n from graded group by 1) g),
  'market_status_values', (select json_object_agg(coalesce(market_status, '(null)'), n) from (select market_status, count(*) n from graded group by 1) s),
  'feed_versions', (select json_object_agg(coalesce(feed_version, '(null)'), n) from (select feed_version, count(*) n from graded group by 1) v),
  'cards', (select json_agg(c order by c.event_date) from (
      select event_id, event_date, count(distinct fight_id) as fights_kept, count(distinct book_id) as books,
             count(*) as kept_rows,
             (select json_object_agg(start_basis, n) from (select start_basis, count(distinct fight_id) n from kept k2
                where k2.event_id = k.event_id group by 1) b) as start_basis
        from kept k group by event_id, event_date) c),
  'capture_gap_minutes_last_24h', (select json_build_object(
      'n', count(gap_min), 'p10', percentile_cont(0.1) within group (order by gap_min),
      'p50', percentile_cont(0.5) within group (order by gap_min),
      'p90', percentile_cont(0.9) within group (order by gap_min)) from gaps where gap_min is not null)
) as quality;
