-- MKT-002 pilot, read 2 of 2: each book's freshest clean two-sided price per
-- bout at T-24h and T-3h (no older than 120 minutes) and at the close (no older
-- than 45 minutes, captured before the start). About 700 rows; returned as CSV
-- with the database's own md5 of that text, so the local copy is provably exact.
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
bouts as (select distinct fight_id, event_id, start_at, start_basis from kept),
anchors as (
  select b.fight_id, b.event_id, a.anchor, a.at, a.max_age
    from bouts b
    cross join lateral (values ('T-24h', b.start_at - interval '24 hours', 120),
                               ('T-3h',  b.start_at - interval '3 hours', 120),
                               ('close', b.start_at, 45)) a(anchor, at, max_age)
),
snap as (
  select distinct on (an.fight_id, an.anchor, k.book_id)
         an.event_id, an.fight_id, an.anchor, k.book_id,
         round(extract(epoch from (an.at - k.retrieved_at)) / 60)::int as age_min, k.am_a, k.am_b, an.max_age
    from anchors an
    join kept k on k.fight_id = an.fight_id and k.retrieved_at <= an.at
   order by an.fight_id, an.anchor, k.book_id, k.retrieved_at desc
),
fresh as (select * from snap where age_min <= max_age),
t as (
  select string_agg(concat_ws(',', event_id, fight_id, anchor, book_id, age_min, am_a, am_b), E'\n'
                    order by fight_id, anchor, book_id) as snap_csv,
         (select string_agg(concat_ws(',', event_id, fight_id, start_basis), E'\n' order by fight_id) from bouts) as bouts_csv,
         count(*) as fresh_rows
    from fresh
)
select fresh_rows, md5(snap_csv) as snap_md5, md5(bouts_csv) as bouts_md5, bouts_csv, snap_csv from t;
