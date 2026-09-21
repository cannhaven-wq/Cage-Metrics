/* ===========================================================================
   alerts.js — when CFL may email somebody about a market, and when it may not.

   Single source of truth, shared by the browser (alert setup UI, the watchlist
   page) and by build/send-alerts.js in Node — the same arrangement edges.js
   has with the snapshotter. Pure: no network, no database, no clock of its own
   (every function takes `now`), so the whole decision layer is testable offline
   and the sender cannot drift from what the UI promised.

   ---------------------------------------------------------------------------
   THE RULE THIS FILE EXISTS FOR
   ---------------------------------------------------------------------------
   An alert must never fire from a market comparison CFL would refuse to print.

   An email is a stronger claim than a number on a page. The member did not go
   looking for it, it arrives with their attention already granted, and it may
   send them to a sportsbook to act on it. So the refusals are at least as
   strict as the display path's, they are NAMED rather than silent, and there
   is no fallback: nothing here widens a cohort, relaxes a threshold or reaches
   for a second-choice baseline in order to have something to say.

   The market refusals themselves live in SQL (`v_fight_alert_market`), beside
   the numbers they refuse. This file honours them and adds the rules that are
   about the ALERT rather than about the market: has it already fired, has the
   cohort changed underneath it, and has it earned the right to speak again.
   =========================================================================== */

(function () {
  'use strict';

  const A = {};

  /* ---------------------------------------------------------------- shape */
  A.KINDS      = ['price_target', 'market_move'];
  A.SIDES      = ['A', 'B'];
  A.DIRECTIONS = ['toward_a', 'toward_b', 'either'];

  // Mirrors the CHECK constraints in alerts_migration.sql. Kept here too so the
  // UI refuses a half-specified alert before the round trip, and so the test
  // can assert the two agree.
  A.MIN_THRESHOLD_PTS = 0.5;   // below this, ordinary capture noise fires it
  A.MAX_THRESHOLD_PTS = 50;
  A.MIN_AMERICAN      = -100000;
  A.MAX_AMERICAN      = 100000;

  /* ------------------------------------------------------------ freshness */
  // A PRICE is an offer and a MOVE is a historical fact, so they do not share a
  // staleness rule. Mirrored in the SQL view; the test asserts both agree,
  // because two numbers meaning one thing is how the two drift.
  A.MAX_PRICE_AGE_MIN = 120;
  A.MAX_MOVE_AGE_MIN  = 1440;
  A.MIN_BOOKS         = 3;     // same floor as every other market surface

  /* -------------------------------------------------------------- refusals */
  // Every reason an alert can decline to fire. A refusal is never silent: the
  // member can see it on the watchlist page and the sender records it. A quiet
  // alert and a broken job look identical from outside, and only one of them is
  // acceptable.
  A.REFUSALS = [
    'paused',                       // the member turned it off
    'no_market_yet',                // CFL holds no prices for this fight
    'fight_settled', 'fight_inactive', 'event_past',
    'no_market', 'thin_book_count',
    'stale_for_price', 'no_best_price',
    'no_broad_capture', 'insufficient_matched_books',
    'no_movement_figure', 'stale_for_move',
    'not_reached',                  // the condition simply is not met
    'already_fired',                // fired, and has not earned another turn
    'cohort_changed_rebaselined',   // the comparison would be dishonest — see below
    'cooldown', 'daily_cap', 'quiet_hours', 'email_disabled'
  ];

  A.isRefusal = r => A.REFUSALS.indexOf(r) !== -1;

  /* ------------------------------------------------------------ validation */
  A.validate = function (a) {
    if (!a || A.KINDS.indexOf(a.kind) === -1) return 'unknown_kind';
    if (a.kind === 'price_target') {
      if (A.SIDES.indexOf(a.side) === -1) return 'side_required';
      if (!isFinite(a.target_american)) return 'target_required';
      if (a.target_american === 0) return 'target_zero';
      if (a.target_american < A.MIN_AMERICAN || a.target_american > A.MAX_AMERICAN) return 'target_range';
      // American odds have no values between -100 and +100. Accepting one makes
      // an alert that can never fire, which looks to the member like a bug.
      if (a.target_american > -100 && a.target_american < 100) return 'target_impossible';
      return null;
    }
    if (!isFinite(a.threshold_pts)) return 'threshold_required';
    if (a.threshold_pts < A.MIN_THRESHOLD_PTS) return 'threshold_too_small';
    if (a.threshold_pts > A.MAX_THRESHOLD_PTS) return 'threshold_too_large';
    if (A.DIRECTIONS.indexOf(a.direction) === -1) return 'direction_required';
    return null;
  };

  /* -------------------------------------------------------- price compare */
  // "Better" is the American number and nothing else (CLAUDE.md). +150 beats
  // +120 beats -110 beats -200, and that ordering is already what `market.js`
  // and `v_fight_market_movement.best_american_*` use, so the test is one >=.
  // There is no implied-probability conversion here on purpose: a second way of
  // ordering prices is a second answer to "which is best".
  A.priceMeetsTarget = function (best, target) {
    if (!isFinite(best) || !isFinite(target)) return false;
    return best >= target;
  };

  /* ---------------------------------------------------- movement direction */
  // movement_pts_a is signed: positive means the market moved TOWARD fighter A
  // (A's vig-free probability rose). A member watching their guy drift wants
  // one direction; a member watching "anything happening here" wants either.
  A.movementInDirection = function (pts, direction) {
    if (!isFinite(pts)) return null;
    if (direction === 'toward_a') return pts;
    if (direction === 'toward_b') return -pts;
    return Math.abs(pts);
  };

  /* ================================================================ decide */
  /*
     evaluate(alert, market, now) -> { fire, reason, value, cohortFp, baselineAt,
                                       rebaseline }

     `market` is one row of v_fight_alert_market. `now` is epoch ms.

     THE RE-ARM, AND WHY IT IS THE INTERESTING PART

     An alert fires once and must then know when to speak again. The obvious
     re-arm subtracts the movement now from the movement when it last fired.
     That is precisely the mixed-cohort error D-012 removed from the product:
     the two readings can be medians over DIFFERENT sets of sportsbooks, and
     their difference is then a fact about bookmaker turnover rather than about
     the market. CFL measured that class of error at up to 12.7 points, with
     three markets that had not moved reading as moving 3+.

     So a movement alert remembers the FINGERPRINT of the cohort it fired over,
     not merely how many books were in it — one book leaving as another joins
     holds the count still and moves the median. If the fingerprint or the
     baseline instant has changed, the alert re-baselines and stays SILENT
     (`cohort_changed_rebaselined`). It costs one notification. The alternative
     costs the member's trust in every notification they ever get.

     A price alert needs none of this: a price is a level, not a comparison
     between two readings, so there is nothing to mix.
  */
  A.evaluate = function (alert, market, now) {
    const out = { fire: false, reason: null, value: null, cohortFp: null,
                  baselineAt: null, rebaseline: false };

    if (!alert || !alert.is_active) { out.reason = 'paused'; return out; }
    if (!market || market.fight_id === null || market.fight_id === undefined) {
      out.reason = 'no_market_yet'; return out;
    }

    // ---- the market's own refusals, honoured exactly as SQL stated them ----
    const marketRefusal = alert.kind === 'price_target'
      ? market.price_refusal
      : market.move_refusal;
    if (marketRefusal) { out.reason = marketRefusal; return out; }

    // Belt and braces on the floor that matters most. The view already applies
    // it; if a future edit to the view ever loses it, the sender still will not
    // email anybody off two books.
    if (Number(market.book_count) < A.MIN_BOOKS) {
      out.reason = 'thin_book_count'; return out;
    }

    // ------------------------------------------------------- price targets --
    if (alert.kind === 'price_target') {
      const best = alert.side === 'A'
        ? Number(market.best_american_a)
        : Number(market.best_american_b);
      out.value = best;
      if (!A.priceMeetsTarget(best, Number(alert.target_american))) {
        out.reason = 'not_reached'; return out;
      }
      // A price alert is a one-shot by design. "Your price is here" is not a
      // thing to say twice about one number, and a price hovering on the
      // threshold would otherwise send an email on every pass.
      if (alert.fire_count > 0) { out.reason = 'already_fired'; return out; }
      out.fire = true;
      return out;
    }

    // ------------------------------------------------------ movement alerts -
    if (Number(market.matched_book_count) < A.MIN_BOOKS ||
        Number(market.cohort_books) < A.MIN_BOOKS) {
      out.reason = 'insufficient_matched_books'; return out;
    }

    const signed = A.movementInDirection(Number(market.movement_pts_a), alert.direction);
    if (signed === null) { out.reason = 'no_movement_figure'; return out; }

    out.value      = signed;
    out.cohortFp   = market.cohort_fp || '';
    out.baselineAt = market.baseline_at || null;

    const threshold = Number(alert.threshold_pts);

    // Never fired: the plain absolute test against the fixed broad baseline.
    if (!alert.fire_count || alert.armed_value === null || alert.armed_value === undefined) {
      if (signed < threshold) { out.reason = 'not_reached'; return out; }
      out.fire = true;
      return out;
    }

    // Fired before. The comparison is only honest if it is the same cohort over
    // the same baseline. Otherwise: re-baseline, say nothing.
    const sameCohort   = (alert.armed_cohort_fp || '') === out.cohortFp;
    const sameBaseline = String(alert.armed_baseline_at || '') === String(out.baselineAt || '');
    if (!sameCohort || !sameBaseline) {
      out.reason = 'cohort_changed_rebaselined';
      out.rebaseline = true;          // the sender stores the new reading, quietly
      return out;
    }

    // Same cohort, same baseline: it speaks again only after a FULL further
    // step in the same direction. Not a fraction of one, and not a wobble back
    // and forth across the line it already reported.
    if (signed < Number(alert.armed_value) + threshold) {
      out.reason = 'already_fired'; return out;
    }
    out.fire = true;
    return out;
  };

  /* ====================================================== quiet / duplicate */
  /*
     Per-ALERT rules are above; these are per-MEMBER, and they are the ones that
     stop a busy fight week turning into forty emails. Three layers, because
     each catches something the others cannot:

       cooldown   no more than one send per member per `cooldown_minutes`,
                  whatever fired. Fifteen alerts crossing at once is one email.
       daily cap  a hard ceiling per UTC day, so a pathological week cannot
                  out-run the cooldown.
       quiet      an optional UTC window. NULL by default, meaning OFF: CFL does
                  not know a member's time zone and will not guess one, because
                  a guessed window silences the alerts somebody asked for at
                  exactly the hours they most wanted them.

     Batching does most of the real work: the sender sends ONE email per member
     per run containing everything that fired, not one email per alert.
  */
  A.DEFAULT_PREFS = {
    email_enabled: true,
    cooldown_minutes: 360,
    max_per_day: 6,
    quiet_start_utc: null,
    quiet_end_utc: null
  };

  A.inQuietHours = function (prefs, now) {
    const p = prefs || A.DEFAULT_PREFS;
    const s = p.quiet_start_utc, e = p.quiet_end_utc;
    if (s === null || s === undefined || e === null || e === undefined) return false;
    if (s === e) return false;                    // a zero-length window is off
    const h = new Date(now).getUTCHours();
    // A window may wrap midnight (22 -> 07), which is the common case for the
    // thing quiet hours are for.
    return s < e ? (h >= s && h < e) : (h >= s || h < e);
  };

  A.maySendToUser = function (prefs, state, now) {
    const p = Object.assign({}, A.DEFAULT_PREFS, prefs || {});
    const st = state || {};
    if (!p.email_enabled) return { ok: false, reason: 'email_disabled' };
    if (A.inQuietHours(p, now)) return { ok: false, reason: 'quiet_hours' };
    if (st.lastSentAt) {
      const mins = (now - Date.parse(st.lastSentAt)) / 60000;
      if (isFinite(mins) && mins < p.cooldown_minutes) {
        return { ok: false, reason: 'cooldown' };
      }
    }
    if ((st.sentToday || 0) >= p.max_per_day) return { ok: false, reason: 'daily_cap' };
    return { ok: true, reason: null };
  };

  /* -------------------------------------------------------- the dedupe key */
  /*
     UNIQUE in the database, and the insert is attempted BEFORE the email is
     sent. Two concurrent passes of the sender — a re-dispatched workflow, a
     retry, two runners — both survive a SELECT-then-INSERT check; only a unique
     index actually decides which one wins. Same lesson as billing_events and
     Stripe's at-least-once delivery (D-018).

     The key is the alert plus its OCCURRENCE NUMBER, never the value that
     triggered it. Keying on the value would mint a fresh key every time the
     price ticked, which is a unique constraint that permits exactly the
     duplicates it was added to stop.
  */
  A.dedupeKey = function (alertId, nextSeq) {
    return 'alert:' + alertId + ':seq:' + nextSeq;
  };

  /* -------------------------------------------------------------- wording */
  // Plain verdict first, plain reason second (CLAUDE.md), and every number
  // carries its book count and its age, exactly as the display path does. No
  // recommendation, no "act now", no implied edge — it reports what happened.
  A.describeFiring = function (alert, market, value) {
    const A_ = market.fighter_a_name || 'Fighter A';
    const B_ = market.fighter_b_name || 'Fighter B';
    const who = alert.side === 'A' ? A_ : B_;
    const books = Number(market.book_count);
    const age = Math.round(Number(market.market_age_minutes));
    const ageTxt = age < 60 ? age + ' min ago'
                 : Math.round(age / 60) + (Math.round(age / 60) === 1 ? ' hour ago' : ' hours ago');

    if (alert.kind === 'price_target') {
      const book = alert.side === 'A' ? market.best_book_a : market.best_book_b;
      return {
        head: who + ' reached ' + A.fmtAmerican(value),
        body: 'Best price across ' + books + ' sportsbooks was ' +
              A.fmtAmerican(value) + ' at ' + (book || 'a book') +
              ', captured ' + ageTxt + '. You asked to hear at ' +
              A.fmtAmerican(alert.target_american) + ' or better. ' +
              'Check the sportsbook before you act — this is the last price CFL ' +
              'captured, not a live quote.'
      };
    }
    const toward = Number(market.movement_pts_a) >= 0 ? A_ : B_;
    return {
      head: 'The ' + A_ + ' v ' + B_ + ' market moved ' +
            Math.abs(Number(market.movement_pts_a)).toFixed(1) + ' points',
      body: 'Measured across the ' + Number(market.matched_book_count) +
            ' sportsbooks quoting at both ends, the market has moved ' +
            Math.abs(Number(market.movement_pts_a)).toFixed(1) +
            ' points toward ' + toward + ' since CFL first held three books on ' +
            'this fight. Prices captured ' + ageTxt + '. This is what the market ' +
            'did — not a view on who wins.'
    };
  };

  A.fmtAmerican = function (n) {
    const v = Number(n);
    if (!isFinite(v)) return '—';
    return v > 0 ? '+' + v : String(v);
  };

  const api = A;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else if (typeof window !== 'undefined') window.cflAlerts = api;
})();
