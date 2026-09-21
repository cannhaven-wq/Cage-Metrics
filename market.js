/* ==========================================================================
   market.js — the single source of truth for everything CFL says about the
   betting market.

   Card Lab (index.html), Fight Lab (fight.html) and Market Lab (market.html)
   all read the market through this file. They must, because the honesty rules
   below are rules about wording and provenance, not about arithmetic, and a
   page that formats its own market numbers can quietly drop one:

     1. A price is never shown without its book count and its age. "56%" is a
        claim; "56%, 6 books, 4 min ago" is an observation.
     2. Movement is measured against the FIRST BROAD CFL CAPTURE — the instant
        CFL first held two-sided prices from three distinct sportsbooks — and
        only over the books quoting at BOTH ends. Never the opening line: CFL
        has never seen a sportsbook opener. This replaced an earlier baseline
        that used CFL's single earliest capture and disclosed the book count
        beside it. Disclosure was not enough. Measured on the live table
        2026-09-21, 22 of 79 fights had exactly ONE book at that instant, and
        against the matched cohort the old baseline overstated a move by up to
        12.7 points — including three fights where a market that had not moved
        at all was reported as moving 3+ points. A caveat a reader may not act
        on is worse than a number we decline to print. See D-012 and
        `market_movement_views.sql`.
     3. EVERY horizon obeys rule 2, not just the baseline. The 24-hour lookback
        and the research forecast-lock comparison are computed over their own
        matched cohorts in SQL (`v_fight_market_horizons`, T-046) and read
        straight from it. Nothing here subtracts one median from another — that
        is how two cohorts get mixed without anyone noticing.
     4. Best price means the best price in the data. `bestSide()` orders by the
        American number and by nothing else — not by affiliate economics, not
        by a house list. If that ever changes, it changes here, in the open,
        and every surface changes with it.
     5. Nothing in this file scores, ranks or recommends a fight. It reports
        what books are posting and how that has changed. There is no CFL
        number, no edge, no confidence and no pick anywhere in it.

   Depends on: _shared.js (window.cflSupabase, cfl.escapeHtml).
   ========================================================================== */
(function () {
  'use strict';

  const M = {};

  // ---------------------------------------------------------------- odds math

  // Vig-free probability -> the American number that probability corresponds
  // to. This is a FAIR price (the market's number with the book's cut taken
  // out), never a price anyone can actually bet, and every surface that shows
  // it must label it "fair".
  M.americanFromProb = function (p) {
    if (p == null || !isFinite(p) || p <= 0 || p >= 1) return null;
    return p >= 0.5 ? -Math.round((p / (1 - p)) * 100)
                    :  Math.round(((1 - p) / p) * 100);
  };

  M.probFromAmerican = function (am) {
    am = +am;
    if (!isFinite(am) || am === 0) return null;
    return am > 0 ? 100 / (am + 100) : (-am) / ((-am) + 100);
  };

  // +150 / -175, always signed, never bare.
  M.fmtAmerican = function (am) {
    if (am == null || !isFinite(+am)) return '—';
    am = Math.round(+am);
    return (am > 0 ? '+' : '') + am;
  };

  // What $100 returns at this price, profit only.
  M.profitOn100 = function (am) {
    am = +am;
    if (!isFinite(am) || am === 0) return null;
    return am > 0 ? am : 10000 / (-am);
  };

  M.fmtPct = function (p, dp) {
    if (p == null || !isFinite(p)) return '—';
    return (p * 100).toFixed(dp == null ? 1 : dp) + '%';
  };

  // ------------------------------------------------------------- freshness

  // How old a quote is, and whether that counts as stale. The capture job runs
  // every few minutes on a fight day and roughly daily otherwise, so the bar
  // moves with the phase. The threshold only decides the word "stale" — the
  // age itself is always shown either way.
  const STALE_FIGHT_DAY_MIN = 180;    //  3 h
  const STALE_OTHERWISE_MIN = 2160;   // 36 h

  M.freshness = function (updatedAt, isFightDay) {
    if (!updatedAt) return null;
    const t = new Date(updatedAt).getTime();
    if (!isFinite(t)) return null;
    const ageMin = Math.max(0, Math.round((Date.now() - t) / 60000));
    const limit = isFightDay ? STALE_FIGHT_DAY_MIN : STALE_OTHERWISE_MIN;
    return { ageMin, stale: ageMin > limit, when: M.fmtAgo(ageMin), at: t };
  };

  M.fmtAgo = function (ageMin) {
    if (ageMin == null || !isFinite(ageMin)) return '';
    if (ageMin < 1)    return 'just now';
    if (ageMin < 60)   return ageMin + ' min ago';
    const h = Math.round(ageMin / 60);
    if (h < 48)        return h + (h === 1 ? ' hour ago' : ' hours ago');
    return Math.round(h / 24) + ' days ago';
  };

  // Short UTC stamp for the provenance line: "Sep 18, 01:55 UTC".
  M.fmtStampUtc = function (ts) {
    if (!ts) return '';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    const mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getUTCMonth()];
    const pad = n => String(n).padStart(2, '0');
    return `${mon} ${d.getUTCDate()}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
  };

  // ------------------------------------------------------- reading a row

  // One row of v_fight_market_movement, read for one corner. Everything a
  // surface needs about that side of the fight, with the caveats attached.
  //
  //   side: 'a' | 'b'
  //
  // Returns null when the fight has no two-sided sportsbook quote at all —
  // which is a real state on a freshly booked fight and is rendered as
  // "no sportsbook line captured yet", never as a zero.
  M.readSide = function (row, side, opts) {
    if (!row) return null;
    const isA = side === 'a' || side === 'A';
    const now  = num(isA ? row.market_p_a     : row.market_p_b);
    if (now == null) return null;
    const h24  = num(isA ? row.market_p_a_24h : row.market_p_b_24h);
    const bestAm  = isA ? row.best_american_a : row.best_american_b;
    const bestBook = isA ? row.best_book_a    : row.best_book_b;
    const fresh = M.freshness(row.last_updated, opts && opts.isFightDay);

    // Movement. The view has already refused it below three matched books, so
    // baseline_p_a and movement_pts_a arrive NULL in that case and everything
    // downstream reads as "not enough comparable books yet". The status is
    // carried through so a surface can say WHICH refusal it is.
    const status   = row.movement_status || 'no_broad_capture';
    const matched  = row.matched_book_count == null ? null : +row.matched_book_count;
    const usable   = status === 'ok' && matched != null && matched >= M.MIN_MATCHED_BOOKS;
    const baseline = usable ? num(isA ? row.baseline_p_a : row.baseline_p_b) : null;
    const movePtsA = usable ? num(row.movement_pts_a) : null;

    return {
      prob: now,
      fairAmerican: M.americanFromProb(now),
      bookCount: row.book_count == null ? null : +row.book_count,
      lastUpdated: row.last_updated,
      fresh,

      // the matched-cohort baseline
      movementStatus: usable ? 'ok' : status,
      baselineProb: baseline,
      baselineAt: row.baseline_at || null,
      baselineBooks: row.baseline_book_count == null ? null : +row.baseline_book_count,
      matchedBooks: matched,
      // signed for THIS corner: side B moves the opposite way to side A
      moveSinceBaseline: movePtsA == null ? null : (isA ? movePtsA : -movePtsA),

      prob24h: h24,
      // T-046: the 24 h move comes from SQL, over its OWN matched cohort. It is
      // NOT `now - h24`: subtracting a matched-cohort median from an all-books
      // median mixes two cohorts, which is the exact defect D-012 removed from
      // the baseline and T-046 removed from here.
      matchedBooks24h: row.book_count_24h == null ? null : +row.book_count_24h,
      movementStatus24h: row.movement_status_24h || 'insufficient_matched_books',
      move24h: (function () {
        const st = row.movement_status_24h;
        const pts = num(row.movement_pts_a_24h);
        if (st !== 'ok' || pts == null) return null;
        return isA ? pts : -pts;
      })(),

      bestAmerican: bestAm == null ? null : +bestAm,
      bestBook: bestBook || null,
      worstAmerican: num(isA ? row.worst_american_a : row.worst_american_b),

      spreadPts: num(row.book_spread_pts),
      captureCount: row.capture_count == null ? null : +row.capture_count,
    };
  };

  // Mirrored in market_movement_views.sql (MIN_BOOKS) and market-movement.js.
  // Change all three together; tests/market-movement.test.js pins it.
  M.MIN_MATCHED_BOOKS = 3;

  function num(v) {
    if (v == null) return null;
    const n = +v;
    return isFinite(n) ? n : null;
  }

  // ------------------------------------------------------------- wording

  // A move, in the only words this product uses for one. Direction is stated
  // relative to the fighter, never as good or bad news for a bettor.
  //   +3.4 -> "Drifted 3.4 pts toward <name>"   (the price on that side shortened)
  //   -3.4 -> "Drifted 3.4 pts away from <name>"
  M.MOVE_NOTABLE_PTS = 2.0;   // below this we call it flat and say so

  M.moveWords = function (pts, name) {
    if (pts == null) return { text: 'not enough comparable books yet', dir: 'none', notable: false };
    const abs = Math.abs(pts);
    if (abs < 0.5) return { text: 'unchanged', dir: 'flat', notable: false };
    const who = name ? ' ' + name : '';
    const dir = pts > 0 ? 'toward' : 'away';
    return {
      text: abs.toFixed(1) + ' pts ' + (pts > 0 ? 'toward' + who : 'away from' + who),
      dir,
      notable: abs >= M.MOVE_NOTABLE_PTS,
    };
  };

  // Signed points, for a compact cell: "+3.4" / "−3.4" / "0.0".
  M.fmtMove = function (pts) {
    if (pts == null) return '—';
    if (Math.abs(pts) < 0.05) return '0.0';
    return (pts > 0 ? '+' : '−') + Math.abs(pts).toFixed(1);
  };

  // How far apart the books are, in plain words. These bands describe the
  // spread; they are not a score and they do not rank the fight.
  M.SPREAD_WIDE_PTS = 4.0;

  M.spreadWords = function (pts, bookCount) {
    if (pts == null || bookCount == null || bookCount < 2) {
      return { text: 'one book quoting', wide: false };
    }
    if (pts >= M.SPREAD_WIDE_PTS) return { text: pts.toFixed(1) + ' pts apart', wide: true };
    if (pts >= 1.5)               return { text: pts.toFixed(1) + ' pts apart', wide: false };
    return { text: 'books agree', wide: false };
  };

  // The provenance sentence that must accompany any movement number, and the
  // reason when there is no movement number. Kept here so no page can print
  // the figure without the working, or print a dash without an explanation.
  M.baselineCaveat = function (sideRead) {
    if (!sideRead) return '';
    if (sideRead.movementStatus !== 'ok') {
      const cur = sideRead.bookCount;
      return sideRead.movementStatus === 'no_broad_capture'
        ? 'No movement figure: CFL has not yet seen this fight priced by ' +
          M.MIN_MATCHED_BOOKS + ' sportsbooks at once' +
          (cur ? ' (' + cur + ' quoting now)' : '') + '.'
        : 'No movement figure: not enough comparable sportsbooks yet. We only ' +
          'compare books quoting at both ends, and fewer than ' +
          M.MIN_MATCHED_BOOKS + ' of them are.';
    }
    const m = sideRead.matchedBooks;
    const cur = sideRead.bookCount;
    const when = M.fmtStampUtc(sideRead.baselineAt);
    const extra = (cur != null && m != null && cur > m)
      ? ' The other ' + (cur - m) + ' quoting now were not there at the start, ' +
        'so they are left out — otherwise a change in who is quoting would read ' +
        'as a change in the price.'
      : '';
    return 'Measured across the ' + m + ' sportsbook' + (m === 1 ? '' : 's') +
           ' quoting both at our first broad capture (' + when + ', when ' +
           M.MIN_MATCHED_BOOKS + '+ books first had this fight priced) and now.' +
           extra + ' That is when CFL started watching properly, not when the ' +
           'market opened — we do not see openers.';
  };

  // ------------------------------------------------------------- loading

  // Movement + best price + spread, one row per fight, for a whole card.
  // Returns {} rather than throwing: a market panel that cannot load is a
  // missing panel, never a broken page.
  M.loadCardMovement = async function (eventId) {
    const sb = window.cflSupabase;
    const out = {};
    if (!sb || eventId == null) return out;
    try {
      const { data, error } = await sb
        .from('v_fight_market_movement')
        .select('*')
        .eq('event_id', eventId);
      if (error) { console.warn('[market] movement view unavailable:', error.message); return out; }
      (data || []).forEach(r => { out[r.fight_id] = r; });
    } catch (e) { console.warn('[market] movement view unavailable:', e.message); }
    return out;
  };

  M.loadFightMovement = async function (fightId) {
    const sb = window.cflSupabase;
    if (!sb || fightId == null) return null;
    try {
      const { data, error } = await sb
        .from('v_fight_market_movement')
        .select('*')
        .eq('fight_id', fightId)
        .limit(1);
      if (error) { console.warn('[market] movement view unavailable:', error.message); return null; }
      return (data && data[0]) || null;
    } catch (e) { console.warn('[market] movement view unavailable:', e.message); return null; }
  };

  // Latest quote from each sportsbook. `by` is 'event_id' or 'fight_id'.
  // Rows come back sorted best-price-first on side A; callers that want side B
  // order re-sort. Only covers cards inside the view's two-week window, so an
  // older fight legitimately returns [].
  M.loadByBook = async function (by, id) {
    const sb = window.cflSupabase;
    if (!sb || id == null) return [];
    try {
      const { data, error } = await sb
        .from('v_fight_odds_latest_by_book')
        .select('*')
        .eq(by, id);
      if (error) { console.warn('[market] per-book view unavailable:', error.message); return []; }
      return (data || []).slice().sort((x, y) => (+y.american_odds_a) - (+x.american_odds_a));
    } catch (e) { console.warn('[market] per-book view unavailable:', e.message); return []; }
  };

  // Is the card today or tomorrow? Decides the staleness bar only.
  M.isFightDay = function (eventDate) {
    if (!eventDate) return false;
    const d = new Date(eventDate + 'T00:00:00Z').getTime();
    if (!isFinite(d)) return false;
    const days = Math.round((d - Date.now()) / 86400000);
    return days <= 1 && days >= -1;
  };

  window.cflMarket = M;
})();
