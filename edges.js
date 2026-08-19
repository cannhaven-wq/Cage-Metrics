// =============================================================================
// edges.js — Cannon Fight Lab shared verdict logic
// =============================================================================
// Single source of truth for edge factors and verdict computation. Used by
// both the browser frontend (index.html) and the Node snapshotter that
// records predictions before each event.
//
// USAGE in browser:
//   <script src="edges.js"></script>
//   const { edges, aProb } = window.cflEdges.computeEdges(a, b, ctx);
//
// USAGE in Node:
//   const cflEdges = require('./edges');
//   const { edges, aProb } = cflEdges.computeEdges(a, b, ctx);
//
// CONTEXT object (`ctx`) shape:
//   {
//     cardioMap: { [fighter_id]: { career: {...}, byWc: { [wc]: {...} } } },
//     fightWeightClass: 'Welterweight' | etc,
//   }
//
// EDGE OBJECT shape (returned by each factor):
//   {
//     factor: 'record' | 'cardio' | 'td_def',
//     favors: 'a' | 'b',
//     pct: number,                                  // 50.0–78.0
//     fighterName: string,                          // who the edge favors
//     desc: string                                  // plain-text description
//                                                   //   excluding the fighter
//                                                   //   name (which is bolded
//                                                   //   separately at render)
//   }
//
// MODEL HISTORY: an earlier version of this module fed ten edges (age, streak,
// loss_streak, post_loss, stance_reach, slpm, td_acc, plus record/cardio/td_def)
// into the Bayesian combiner. Backtest against 8,533 historical fights
// (research/subset-test.js) showed those seven extra factors sat at 52–57%
// per-fire accuracy and acted as correlated noise that diluted the strong
// signals. They were removed on 2026-05-17. That backtest was itself later
// found to be hindsight-biased — it scored old fights using each fighter's
// CURRENT career stats — so read its accuracy figures as an upper bound, not
// as a result.
//
// Cardio was retired on 2026-08-19 (see cardioEdge for the evidence). Two
// factors still fire: record and td_def. Both are inherited from that same
// superseded backtest and have not been re-validated point-in-time, which is
// why the verdict this module produces is labelled provisional on edges.html.
// CFL's published picks come from the audited engine, not from here.
// =============================================================================

(function (root) {
  'use strict';

  // =========================================================================
  // Constants
  // =========================================================================

  const STYLE_THRESHOLDS = {
    // Capability gate used by willHaveWrestling. Lower bar by design — asks
    // "does this fighter shoot AT ALL?" A career td_avg of even 1 attempt per
    // 15 minutes makes grappling relevant enough to apply td_def.
    TD_LOW: 1.0,

    // Dominance-ratio classifier thresholds (used by classifyStyle).
    // These represent the "real producer" line — above this is a meaningful
    // contributor in that phase. Calibrated to roughly match v_fighter_style's
    // SQL thresholds (90 grapp_score / 16 strk_score per round) translated
    // into the career-average fields available here:
    //   td_avg is takedown ATTEMPTS per 15 minutes. ~2.5 attempts/15 means
    //   landing ~1 per round at typical accuracy, the rough cutoff for
    //   "real grappler" output.
    //   slpm of ~3.2 = ~16 sig strikes landed per round = SQL striker line.
    GRAPP_REAL: 2.5,
    STRK_REAL:  3.2,
  };

  const CARDIO_TIER_RANK = {
    tireless: 5, steady: 4, tapers: 3, fades: 2, collapses: 1,
  };

  // =========================================================================
  // Style classifier & capability gates
  // =========================================================================

  // classifyStyle — JS implementation of the SQL v_fighter_style classifier.
  // Returns 'grappler' | 'striker' | 'hybrid' | 'low_volume' | 'unknown'.
  //
  // ACCURACY NOTE: this works from the career-aggregate fields on the fighters
  // table (td_avg = attempts/15min, slpm = strikes landed/min). The SQL view
  // v_fighter_style is more accurate because it uses td_LANDED + control time
  // from per-round data. The browser homepage prefers the SQL view via batched
  // lookup; this function exists as a fallback (and is what the Node
  // snapshotter uses, since that environment doesn't have the view loaded).
  //
  // Logic mirrors v_fighter_style v2: normalize each phase against its
  // "real producer" threshold, then look at dominance. Avoids the trap that
  // pushed Khabib (overwhelming grappler with modest striking) into "hybrid".
  function classifyStyle(fighter) {
    const td = fighter.td_avg;
    const slpm = fighter.slpm;
    if (td == null && slpm == null) return 'unknown';
    if (td == null || slpm == null) return 'hybrid';

    const grappNorm = td   / STYLE_THRESHOLDS.GRAPP_REAL;
    const strkNorm  = slpm / STYLE_THRESHOLDS.STRK_REAL;

    // Both essentially nothing on both axes → low-volume fighter
    if (grappNorm < 0.4 && strkNorm < 0.6) return 'low_volume';

    // Both clear the "real producer" bar AND neither dominates 2:1 → hybrid
    if (grappNorm >= 1.0 && strkNorm >= 1.0
        && grappNorm < 2 * strkNorm
        && strkNorm  < 2 * grappNorm) {
      return 'hybrid';
    }

    // Grappling clears threshold AND dominates striking 2:1 (or strk near zero)
    if (grappNorm >= 1.0
        && (strkNorm < 0.001 || grappNorm >= 2 * strkNorm)) {
      return 'grappler';
    }

    // Striking clears threshold AND dominates grappling 2:1 (or grapp near zero)
    if (strkNorm >= 1.0
        && (grappNorm < 0.001 || strkNorm >= 2 * grappNorm)) {
      return 'striker';
    }

    // Below threshold on the dominant axis: classify by which has more
    // normalized output (catches O'Malley-style: just-under-threshold striker
    // with zero grappling — should be 'striker', not 'low_volume').
    if (strkNorm > grappNorm) return 'striker';
    if (grappNorm > strkNorm) return 'grappler';
    return 'low_volume';
  }

  function willHaveWrestling(a, b) {
    const tdA = a.td_avg == null ? 0 : a.td_avg;
    const tdB = b.td_avg == null ? 0 : b.td_avg;
    return tdA >= STYLE_THRESHOLDS.TD_LOW || tdB >= STYLE_THRESHOLDS.TD_LOW;
  }

  // =========================================================================
  // Cardio lookup helper
  // =========================================================================

  function cardioFor(fighterId, weightClass, cardioMap) {
    if (!cardioMap) return null;
    const slot = cardioMap[fighterId];
    if (!slot) return null;
    if (weightClass && slot.byWc && slot.byWc[weightClass] && slot.byWc[weightClass].tier_word) {
      return Object.assign({}, slot.byWc[weightClass], { source: 'weight_class' });
    }
    if (slot.career && slot.career.tier_word) {
      return Object.assign({}, slot.career, { source: 'career' });
    }
    return null;
  }

  // =========================================================================
  // EDGE FACTORS
  // =========================================================================

  function recordEdge(a, b) {
    const aw = a.wins || 0, al = a.losses || 0;
    const bw = b.wins || 0, bl = b.losses || 0;
    const aTotal = aw + al;
    const bTotal = bw + bl;
    if (aTotal + bTotal < 3) return null;
    const aRate = (aw + 2) / (aTotal + 4);
    const bRate = (bw + 2) / (bTotal + 4);
    const gap = Math.abs(aRate - bRate);
    if (gap < 0.08) return null;
    let pct;
    if (gap >= 0.40)      pct = 72.0;
    else if (gap >= 0.25) pct = 70.0;
    else if (gap >= 0.15) pct = 65.0;
    else                  pct = 60.0;
    const aBetter = aRate > bRate;
    const aRec = aw + '-' + al;
    const bRec = bw + '-' + bl;
    return {
      factor: 'record',
      favors: aBetter ? 'a' : 'b',
      pct,
      fighterName: aBetter ? a.name : b.name,
      desc: 'has stronger pro record (' + (aBetter ? aRec : bRec) + ' vs ' + (aBetter ? bRec : aRec) + ')',
    };
  }

  function tdDefEdge(a, b) {
    if (a.td_def == null || b.td_def == null) return null;
    if (!willHaveWrestling(a, b)) return null;
    const gap = Math.abs(a.td_def - b.td_def);
    if (gap < 10) return null;
    let pct;
    if (gap >= 30)      pct = 56.0;
    else if (gap >= 20) pct = 54.0;
    else                pct = 52.5;
    const aBetter = a.td_def > b.td_def;
    return {
      factor: 'td_def',
      favors: aBetter ? 'a' : 'b',
      pct,
      fighterName: aBetter ? a.name : b.name,
      desc: 'has ' + gap + 'pp better takedown defense',
    };
  }

  // RETIRED 2026-08-19 — cardio does not predict winners.
  //
  // This factor used to fire at a 3+ tier gap and claim 54-58%. That number
  // came from a backtest with two flaws: it scored past fights using each
  // fighter's cardio as measured TODAY (hindsight), and the underlying view
  // counted every round as a full five minutes regardless of when the fight
  // actually ended. Rebuilt point-in-time and re-measured on fights the market
  // priced even — the only test that separates a real signal from re-reading
  // the favourite — cardio lands at 50.2%. A coin flip. Even restricted to
  // fights that genuinely reached round three it is 54.1% on 218 fights, with
  // a confidence range that still includes 50.
  //
  // What cardio DOES predict is how long a fight lasts, which is a different
  // market and is not a win-probability input. It stays on fighter pages and
  // in the matchup context as description; it no longer moves a verdict.
  //
  // Kept as a stub rather than deleted so the export surface and the ctx shape
  // stay stable for the cfl-snapshotter service, which shares this module.
  function cardioEdge() {
    return null;
  }

  // =========================================================================
  // Verdict computation
  // =========================================================================

  function computeEdges(a, b, ctx) {
    ctx = ctx || {};
    const cardioMap = ctx.cardioMap || null;
    const wc = ctx.fightWeightClass || null;
    // Optional whitelist of factor names. If absent, all three factors run
    // (current default). Used by event.html's model selector to compute
    // record-only / cardio-only / td-def-only variants for "What if the model
    // only looked at X?" comparisons.
    const allow = ctx.factors && ctx.factors.length
      ? new Set(ctx.factors)
      : null;
    const pass = (e) => (e && (!allow || allow.has(e.factor))) ? e : null;

    const edges = [
      pass(recordEdge(a, b)),
      pass(cardioEdge(a, b, cardioMap, wc)),
      pass(tdDefEdge(a, b)),
    ].filter(Boolean);

    // Bayesian combination of edges. `steps` records the running fighter-A
    // probability after each edge (pre-cap) so callers can draw a waterfall of
    // how the verdict was built without re-deriving the math.
    let aProb = 0.5;
    const steps = [];
    for (let i = 0; i < edges.length; i++) {
      const e = edges[i];
      const factor = e.favors === 'a' ? (e.pct / 100) : (1 - e.pct / 100);
      aProb = (aProb * factor) / (aProb * factor + (1 - aProb) * (1 - factor));
      steps.push({
        factor: e.factor,
        favors: e.favors,
        pct: e.pct,
        fighterName: e.fighterName,
        aProbAfter: aProb,
      });
    }
    // Cap to prevent stacked-edges runaway.
    const strongest = edges.length ? Math.max.apply(null, edges.map(function (e) { return e.pct; })) / 100 : 0.5;
    const cap = Math.min(0.78, strongest + 0.06);
    const uncappedAProb = aProb;
    if (aProb > cap) aProb = cap;
    if (aProb < 1 - cap) aProb = 1 - cap;
    const capped = aProb !== uncappedAProb;

    return { edges, aProb, steps, capped };
  }

  // =========================================================================
  // Public API
  // =========================================================================

  const api = {
    // Constants
    STYLE_THRESHOLDS,
    CARDIO_TIER_RANK,
    // Helpers
    classifyStyle,
    willHaveWrestling,
    cardioFor,
    // Edge factors (exported for testing / debugging)
    recordEdge,
    tdDefEdge,
    cardioEdge,
    // Main entry point
    computeEdges,
  };

  // UMD-style export
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.cflEdges = api;
  }
})(typeof window !== 'undefined' ? window : this);
