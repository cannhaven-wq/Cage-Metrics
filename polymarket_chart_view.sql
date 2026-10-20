-- =============================================================================
-- polymarket_chart_view.sql — Polymarket's price history, for the opt-in line.
-- Applied 2026-10-20. Safe to re-run.
-- =============================================================================
-- PLAIN ENGLISH: Polymarket is a prediction market, not a sportsbook. Its
-- price is what traders last paid, not a number a book is offering. So it
-- NEVER joins the sportsbook middle line, the best price, the movement figures
-- or the alerts — every one of those reads v_odds_books_sportsbooks, which
-- excludes it by name, and this file changes none of them.
--
-- What it does is let a reader who asks for it (a switch, off by default) see
-- Polymarket's own line on its own chart. That matters most on a fight no
-- sportsbook has priced yet, which otherwise shows nothing at all.
--
-- What is refused, and why:
--   * live (in-fight) quotes and any market not marked open — same rule as
--     v_fight_market_quotes;
--   * captures after the opening bell, where the bell is known, or more than
--     two days after the card date — a price after the bell is not a
--     pre-fight price;
--   * a settled-looking market: either side at 1% or less. A resolved market
--     reads 0/100 (stored as ±199900, HANDOFF_EVENT_FLOW L3-EF-3), and drawing
--     it would show a "move" that is really the result.
--
-- Single-fight view, like v_fight_chart_series: query it with one literal
-- fight_id. It is a self-join on idx_fight_odds_fight_book_time.
-- =============================================================================

CREATE OR REPLACE VIEW public.v_fight_polymarket_series AS
SELECT
  a.fight_id,
  a.captured_at                                     AS at,
  a.implied_prob / (a.implied_prob + b.implied_prob) AS p_a,
  a.american_odds                                   AS american_odds_a,
  b.american_odds                                   AS american_odds_b
FROM public.fight_odds a
JOIN public.fight_odds b
  ON b.fight_id = a.fight_id AND b.book_id = a.book_id
 AND b.captured_at = a.captured_at AND b.side = 'B'
JOIN public.odds_books ob ON ob.id = a.book_id AND lower(ob.name) = 'polymarket'
JOIN public.fights f ON f.id = a.fight_id
JOIN public.events e ON e.id = f.event_id
WHERE a.side = 'A'
  AND a.implied_prob > 0 AND b.implied_prob > 0
  AND a.is_live IS NOT TRUE AND b.is_live IS NOT TRUE
  AND (a.market_status IS NULL OR a.market_status = 'open')
  AND (b.market_status IS NULL OR b.market_status = 'open')
  AND a.captured_at < COALESCE(f.bell_at, (e.event_date + 2)::timestamptz)
  AND a.implied_prob / (a.implied_prob + b.implied_prob) > 0.01
  AND a.implied_prob / (a.implied_prob + b.implied_prob) < 0.99;

COMMENT ON VIEW public.v_fight_polymarket_series IS
  'Polymarket price history per fight, pre-bell, open markets only, settled '
  '(<=1% / >=99%) prices refused. A prediction market, never a sportsbook: '
  'nothing that computes a consensus, best price or movement reads this view.';

REVOKE ALL ON TABLE public.v_fight_polymarket_series FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.v_fight_polymarket_series TO anon, authenticated;
