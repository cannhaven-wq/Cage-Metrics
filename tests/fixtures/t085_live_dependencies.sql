-- Production definitions of the views v_fight_chart_series depends on,
-- captured with pg_get_viewdef on 2026-10-13. Test fixture only: lets the
-- T-085 migration and its rollback run against a throwaway Postgres.
-- v_fight_locked_forecast is stubbed empty (it only feeds the 'lock' horizon).
CREATE VIEW public.v_fight_locked_forecast AS SELECT NULL::bigint AS fight_id, NULL::timestamptz AS locked_at WHERE false;
CREATE VIEW public.v_odds_books_sportsbooks AS
 SELECT id,
    name,
    short_code
   FROM odds_books
  WHERE name !~~* '%consensus%'::text AND (lower(name) <> ALL (ARRAY['polymarket'::text, 'kalshi'::text]));

CREATE VIEW public.v_fight_market_quotes AS
 SELECT a.fight_id,
    a.book_id,
    a.captured_at AS quoted_at,
    a.implied_prob / (a.implied_prob + b.implied_prob) AS fair_a,
    b.implied_prob / (a.implied_prob + b.implied_prob) AS fair_b,
    a.american_odds AS american_odds_a,
    b.american_odds AS american_odds_b,
    a.retrieved_at
   FROM fight_odds a
     JOIN fight_odds b ON b.fight_id = a.fight_id AND b.book_id = a.book_id AND b.captured_at = a.captured_at AND b.side = 'B'::bpchar
     JOIN v_odds_books_sportsbooks sb ON sb.id = a.book_id
  WHERE a.side = 'A'::bpchar AND a.captured_at > '2010-01-01 00:00:00+00'::timestamp with time zone AND a.implied_prob IS NOT NULL AND a.implied_prob > 0::numeric AND b.implied_prob IS NOT NULL AND b.implied_prob > 0::numeric AND a.is_live IS NOT TRUE AND b.is_live IS NOT TRUE AND (a.market_status IS NULL OR a.market_status = 'open'::text) AND (b.market_status IS NULL OR b.market_status = 'open'::text);

CREATE VIEW public.v_fight_market_broad_baseline AS
 WITH first_seen AS (
         SELECT v_fight_market_quotes.fight_id,
            v_fight_market_quotes.book_id,
            min(v_fight_market_quotes.quoted_at) AS first_quoted_at
           FROM v_fight_market_quotes
          GROUP BY v_fight_market_quotes.fight_id, v_fight_market_quotes.book_id
        ), ranked AS (
         SELECT first_seen.fight_id,
            first_seen.book_id,
            first_seen.first_quoted_at,
            row_number() OVER (PARTITION BY first_seen.fight_id ORDER BY first_seen.first_quoted_at, first_seen.book_id) AS book_rank
           FROM first_seen
        )
 SELECT fight_id,
    first_quoted_at AS baseline_at,
    3 AS min_books
   FROM ranked
  WHERE book_rank = 3;

CREATE VIEW public.v_fight_market_horizon_cohorts AS
 WITH fights_seen AS (
         SELECT DISTINCT v_fight_market_quotes.fight_id
           FROM v_fight_market_quotes
        ), h AS (
         SELECT v_fight_market_broad_baseline.fight_id,
            'broad_baseline'::text AS horizon,
            v_fight_market_broad_baseline.baseline_at AS as_of
           FROM v_fight_market_broad_baseline
        UNION ALL
         SELECT fights_seen.fight_id,
            'h24'::text AS text,
            now() - '24:00:00'::interval
           FROM fights_seen
        UNION ALL
         SELECT v_fight_locked_forecast.fight_id,
            'lock'::text AS text,
            v_fight_locked_forecast.locked_at
           FROM v_fight_locked_forecast
          WHERE v_fight_locked_forecast.locked_at IS NOT NULL
        ), then_cohort AS (
         SELECT DISTINCT ON (h.fight_id, h.horizon, q.book_id) h.fight_id,
            h.horizon,
            h.as_of,
            q.book_id,
            q.fair_a AS then_fair_a,
            q.quoted_at AS then_quoted_at
           FROM h
             JOIN v_fight_market_quotes q ON q.fight_id = h.fight_id AND q.quoted_at <= h.as_of
          ORDER BY h.fight_id, h.horizon, q.book_id, q.quoted_at DESC
        ), now_cohort AS (
         SELECT DISTINCT ON (v_fight_market_quotes.fight_id, v_fight_market_quotes.book_id) v_fight_market_quotes.fight_id,
            v_fight_market_quotes.book_id,
            v_fight_market_quotes.fair_a AS now_fair_a,
            v_fight_market_quotes.quoted_at AS now_quoted_at
           FROM v_fight_market_quotes
          ORDER BY v_fight_market_quotes.fight_id, v_fight_market_quotes.book_id, v_fight_market_quotes.quoted_at DESC
        )
 SELECT t.fight_id,
    t.horizon,
    t.as_of,
    t.book_id,
    t.then_fair_a,
    t.then_quoted_at,
    n.now_fair_a,
    n.now_quoted_at
   FROM then_cohort t
     JOIN now_cohort n ON n.fight_id = t.fight_id AND n.book_id = t.book_id;

CREATE VIEW public.v_fight_chart_meta AS
 WITH cohort AS (
         SELECT v_fight_market_horizon_cohorts.fight_id,
            count(*)::integer AS cohort_books
           FROM v_fight_market_horizon_cohorts
          WHERE v_fight_market_horizon_cohorts.horizon = 'broad_baseline'::text
          GROUP BY v_fight_market_horizon_cohorts.fight_id
        ), span AS (
         SELECT q.fight_id,
            min(q.quoted_at) AS first_seen_at,
            max(q.quoted_at) AS last_seen_at,
            count(DISTINCT q.book_id)::integer AS books_ever
           FROM v_fight_market_quotes q
          GROUP BY q.fight_id
        )
 SELECT s.fight_id,
    b.baseline_at AS window_start,
    s.last_seen_at AS window_end,
    s.first_seen_at,
    s.books_ever,
    COALESCE(c.cohort_books, 0) AS cohort_books,
    3 AS min_books,
        CASE
            WHEN b.fight_id IS NULL THEN 'no_broad_capture'::text
            WHEN COALESCE(c.cohort_books, 0) < 3 THEN 'insufficient_matched_books'::text
            ELSE 'ok'::text
        END AS series_status,
    'fixed_cohort_median_vigfree_v1'::text AS series_method
   FROM span s
     LEFT JOIN v_fight_market_broad_baseline b ON b.fight_id = s.fight_id
     LEFT JOIN cohort c ON c.fight_id = s.fight_id;
