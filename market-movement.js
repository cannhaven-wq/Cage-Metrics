/* ==========================================================================
   Cannon Fight Lab — market movement, the only place it is described
   --------------------------------------------------------------------------
   Single source of truth for turning a `v_fight_market_movement` row into the
   words a reader sees. Loaded in the browser as window.cflMovement and
   require()-able in Node, so a page and a test cannot drift apart on what a
   movement number is allowed to claim.

   THE RULE THIS MODULE ENFORCES

   CFL knows when CFL first captured a price. CFL has never observed a
   sportsbook opener. Nothing here — and nothing downstream of here — may say
   "opening line", "open", "opened at" or "opening market". The baseline is the
   FIRST BROAD CFL CAPTURE: the instant CFL first held two-sided prices from
   three distinct real sportsbooks.

   Movement is measured over the MATCHED BOOK COHORT — the books quoting at
   both the baseline and now — and is refused outright below MIN_MATCHED_BOOKS.
   It is never widened to a bigger cohort to produce a number, because a
   one-book baseline against a six-book present is a change in who is being
   asked, not a change in the answer. Measured on the live table 2026-09-21:
   28% of fights had exactly one sportsbook at CFL's earliest capture, and the
   retired method overstated a move by as much as 12.7 points, including three
   fights where a market that had not moved at all was reported as moving 3+.

   row shape (from v_fight_market_movement, all optional):
     {
       movement_status: 'ok' | 'insufficient_matched_books' | 'no_broad_capture',
       movement_pts_a, baseline_p_a, matched_current_p_a,
       baseline_at, baseline_quote_at, last_updated, oldest_current_quote_at,
       baseline_book_count, current_book_count | book_count, matched_book_count,
       movement_method
     }
   ========================================================================== */
(function () {
  // Mirrored in market_movement_views.sql (MIN_BOOKS, literal 3 in each view)
  // and pinned by tests/market-movement.test.js. Change all three together.
  const MIN_MATCHED_BOOKS = 3;

  // Under this, a move is noise dressed as news and reads as "held steady".
  const FLAT_PTS = 1.0;

  // Wording that would claim CFL saw the sportsbook opener. Exported so copy
  // guards elsewhere can reuse one list.
  const FORBIDDEN_BASELINE_WORDS = [
    'opening line', 'opening price', 'opening market', 'the open',
    'opened at', 'market open', 'line open'
  ];

  const PLAIN_BASELINE = 'since CFL first saw 3+ sportsbooks';
  const SHORT_BASELINE = 'since first broad capture';

  function num(v) { return (v === null || v === undefined || v === '') ? null : Number(v); }

  function ageMinutes(iso, now) {
    if (!iso) return null;
    const t = Date.parse(iso);
    if (!isFinite(t)) return null;
    return Math.max(0, Math.round(((now || Date.now()) - t) / 60000));
  }

  function ageWords(mins) {
    if (mins === null) return null;
    if (mins < 60) return mins + ' min ago';
    const h = Math.round(mins / 60);
    if (h < 48) return h + ' hr ago';
    return Math.round(h / 24) + ' days ago';
  }

  /* ------------------------------------------------------------------------
     describeMovement(row, opts) -> the three disclosure layers, or an honest
     refusal. Never returns a number it cannot defend.

       { ok, status, plain, value, detail, method, books:{...}, at:{...} }
     ------------------------------------------------------------------------ */
  function describeMovement(row, opts) {
    const o = opts || {};
    const now = o.now || Date.now();
    const nameA = o.fighterA || 'the favourite side';
    const nameB = o.fighterB || 'the other side';

    const status = (row && row.movement_status) || 'no_broad_capture';
    const matched = num(row && row.matched_book_count) || 0;
    const baseBooks = num(row && row.baseline_book_count) || 0;
    const curBooks = num(row && (row.current_book_count !== undefined
      ? row.current_book_count : row.book_count)) || 0;

    const books = {
      baseline: baseBooks, current: curBooks, matched: matched,
      minimum: MIN_MATCHED_BOOKS
    };
    const at = {
      baseline: (row && (row.baseline_quote_at || row.baseline_at)) || null,
      current: (row && row.last_updated) || null,
      oldestCurrent: (row && row.oldest_current_quote_at) || null
    };

    // ---- the honest refusals. No fallback number, ever. -------------------
    if (status === 'no_broad_capture' || !at.baseline) {
      return {
        ok: false, status: 'no_broad_capture',
        plain: 'Movement unavailable',
        value: null,
        detail: 'CFL has not yet seen this fight priced by ' + MIN_MATCHED_BOOKS +
                ' different sportsbooks at once, so there is nothing comparable to ' +
                'measure against. ' + (curBooks ? curBooks : 'No') +
                ' sportsbook' + (curBooks === 1 ? '' : 's') + ' quoting now.',
        method: null, books: books, at: at
      };
    }
    if (status !== 'ok' || matched < MIN_MATCHED_BOOKS) {
      return {
        ok: false, status: 'insufficient_matched_books',
        plain: 'Movement unavailable',
        value: null,
        detail: 'Not enough comparable sportsbooks yet. ' + matched + ' of the ' +
                baseBooks + ' book' + (baseBooks === 1 ? '' : 's') +
                ' CFL first saw are still quoting; we need ' + MIN_MATCHED_BOOKS +
                ' to compare like with like, and we do not widen the comparison ' +
                'to manufacture a number.',
        method: null, books: books, at: at
      };
    }

    // ---- the defensible number -------------------------------------------
    const pts = num(row.movement_pts_a);
    if (pts === null || !isFinite(pts)) {
      return {
        ok: false, status: 'insufficient_matched_books',
        plain: 'Movement unavailable',
        value: null,
        detail: 'Not enough comparable sportsbooks yet.',
        method: null, books: books, at: at
      };
    }

    const mag = Math.abs(pts);
    const toward = pts > 0 ? nameA : nameB;
    const plain = mag < FLAT_PTS
      ? 'Books have held steady'
      : 'Books moved toward ' + toward;

    const curAge = ageWords(ageMinutes(at.current, now));
    const baseAge = ageWords(ageMinutes(at.baseline, now));

    const detail =
      'Compared using ' + matched + ' sportsbook' + (matched === 1 ? '' : 's') +
      ' present both when CFL first saw ' + MIN_MATCHED_BOOKS +
      '+ books and in the market now' +
      (curBooks > matched
        ? ' (' + curBooks + ' quote now in total; the ' + (curBooks - matched) +
          ' that were not there at the start are left out of the comparison so ' +
          'a change in who is quoting cannot read as a change in the price)'
        : '') +
      '. Each book is de-vigged on its own two prices, then we take the middle ' +
      'book. Baseline ' + (baseAge || 'time unknown') +
      ', latest ' + (curAge || 'time unknown') + '.';

    return {
      ok: true, status: 'ok',
      plain: plain,
      value: {
        pts: pts,
        text: (pts > 0 ? '+' : pts < 0 ? '−' : '') + mag.toFixed(1) + ' pts',
        label: SHORT_BASELINE,
        longLabel: PLAIN_BASELINE,
        baselinePct: num(row.baseline_p_a) === null ? null : num(row.baseline_p_a) * 100,
        currentPct: num(row.matched_current_p_a) === null ? null : num(row.matched_current_p_a) * 100
      },
      detail: detail,
      method: (row && row.movement_method) || 'matched_cohort_median_vigfree_v1',
      books: books, at: at
    };
  }

  /* ------------------------------------------------------------------------
     describeBestPrice(row, side) — a price is only "best observed" if it names
     the book it came from and says how old it is. Ordering is the American
     number and nothing else; no commercial relationship reaches it.
     ------------------------------------------------------------------------ */
  function describeBestPrice(row, side, opts) {
    const o = opts || {};
    const a = String(side || 'a').toLowerCase() === 'b' ? 'b' : 'a';
    const price = num(row && row['best_american_' + a]);
    const book = row && row['best_book_' + a];
    const at = (row && row.last_updated) || null;
    if (price === null || !book) {
      return { ok: false, plain: 'No sportsbook price captured yet',
               price: null, book: null, age: null };
    }
    const mins = ageMinutes(at, o.now || Date.now());
    return {
      ok: true,
      // "best observed", not "best available": CFL reports what it captured,
      // not what a given reader can actually bet.
      plain: 'Best observed price',
      price: (price > 0 ? '+' : '') + price,
      book: book,
      age: ageWords(mins),
      ageMinutes: mins,
      note: 'Highest American price CFL has captured across ' +
            (num(row && row.book_count) || 0) + ' sportsbooks. Ranked on the ' +
            'number alone — CFL takes no payment from any sportsbook, and ' +
            'no sportsbook can buy this position.'
    };
  }

  /* ------------------------------------------------------------------------
     describeBookSpread(row) — "books disagree" is not a finding unless the
     measurement is stated. This is max minus min of the de-vigged A-side
     price across the current books, in probability points.
     ------------------------------------------------------------------------ */
  function describeBookSpread(row) {
    const pts = num(row && row.book_spread_pts);
    const n = num(row && row.book_count) || 0;
    if (pts === null || n < 2) {
      return { ok: false, plain: 'Only one sportsbook quoting',
               value: null, detail: 'A price range needs at least two books.' };
    }
    return {
      ok: true,
      plain: pts >= 3 ? 'Books disagree' : 'Books broadly agree',
      value: pts.toFixed(1) + ' pts',
      detail: 'Widest gap between the ' + n + ' sportsbooks quoting now, after ' +
              'removing each book’s margin. ' + pts.toFixed(1) +
              ' points between the highest and the lowest.'
    };
  }

  const api = {
    MIN_MATCHED_BOOKS, FLAT_PTS, FORBIDDEN_BASELINE_WORDS,
    PLAIN_BASELINE, SHORT_BASELINE,
    describeMovement, describeBestPrice, describeBookSpread,
    ageMinutes, ageWords
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflMovement = api;
})();
