// =============================================================================
// distanceEdges.js — Cannon Fight Lab distance/finish predictor
// =============================================================================
// Predicts P(fight goes the distance) for a given matchup. Sister module to
// edges.js (which predicts the winner). Phase-1 heuristic — three factors,
// additive deltas on top of a division base rate. Refined via the same
// validation flow as edges.js (research/validate.js).
//
// USAGE in browser:
//   <script src="distanceEdges.js"></script>
//   const { factors, distanceProb } = window.cflDistanceEdges.computeDistance(a, b, fight, ctx);
//
// USAGE in Node:
//   const cflDistanceEdges = require('./distanceEdges');
//   const { factors, distanceProb } = cflDistanceEdges.computeDistance(a, b, fight, ctx);
//
// CONTEXT object (`ctx`) shape:
//   {
//     cardioMap: { [fighter_id]: { career: {tier_word,...}, byWc: { [wc]: {...} } } }
//   }
//
// FACTOR shape (each function returns one of these or null):
//   {
//     factor:   'division' | 'cardio' | 'rounds',  // machine-readable id
//     delta_pp: number,                              // points to add to base rate
//     desc:     string,                              // plain-text reason
//   }
//
// LIMITATIONS:
// - Division base rates are hardcoded approximations. v2 should pull live
//   rates from v_finish_rate_by_division and pass them in via ctx.
// - No fighter-specific finish-rate factor yet (would need a v_fighter_finish_rate
//   view aggregating per-fighter KO/Sub/Decision history).
// - No style-matchup factor yet (would need styleMap loaded on the page).
// =============================================================================

(function (root) {
  'use strict';

  // Empirical baseline rates for the fraction of fights in each division that
  // go to a decision. v2 values calibrated against actual UFC history
  // (research/results.md, "Per-division accuracy + actual base rate" table).
  // Men's divisions are measured; Women's are still hand-estimates (small
  // sample sizes; below the validate.js >=50-fight cutoff).
  const DIVISION_DISTANCE_RATE = {
    'Heavyweight':            0.32,  // v2: was 0.25, measured 32.2%
    'Light Heavyweight':      0.36,  // v2: was 0.40, measured 36.3%
    'Middleweight':           0.40,  // v2: was 0.45, measured 40.1%
    'Welterweight':           0.47,  // v2: was 0.50, measured 47.1%
    'Lightweight':            0.48,  // v2: was 0.52, measured 47.8%
    'Featherweight':          0.54,  // v2: was 0.58, measured 53.7%
    'Bantamweight':           0.55,  // v2: was 0.62, measured 55.5%
    'Flyweight':              0.58,  // v2: was 0.65, measured 57.8%
    'Strawweight':            0.66,  // v2: was 0.65, measured 66.4%
    "Women's Strawweight":    0.78,  // hand-estimate, small sample
    "Women's Flyweight":      0.72,  // hand-estimate
    "Women's Bantamweight":   0.68,  // hand-estimate
    "Women's Featherweight":  0.65,  // hand-estimate
    'Catch Weight':           0.49,  // v2: was 0.50, measured 48.7%
    'Open Weight':            0.07,  // v2: was 0.30, measured 7.1% (early UFC tournaments)
  };

  const CARDIO_TIER_RANK = {
    tireless: 5, steady: 4, tapers: 3, fades: 2, collapses: 1,
  };

  function baseDistanceRate(weightClass) {
    if (weightClass && DIVISION_DISTANCE_RATE[weightClass] != null) {
      return DIVISION_DISTANCE_RATE[weightClass];
    }
    return 0.50;
  }

  function cardioFor(fighterId, weightClass, cardioMap) {
    if (!cardioMap) return null;
    const slot = cardioMap[fighterId];
    if (!slot) return null;
    if (weightClass && slot.byWc && slot.byWc[weightClass] && slot.byWc[weightClass].tier_word) {
      return slot.byWc[weightClass];
    }
    if (slot.career && slot.career.tier_word) return slot.career;
    return null;
  }

  // CARDIO GAP — when one fighter has a much better cardio tier, the other
  // fades in R3+, which historically translates to late finishes (TKOs from
  // accumulated damage on the slower fighter, late submissions when grappling
  // is on the table). So a big gap REDUCES distance probability.
  function cardioFactor(a, b, cardioMap, weightClass) {
    const ca = cardioFor(a.id, weightClass, cardioMap);
    const cb = cardioFor(b.id, weightClass, cardioMap);
    if (!ca || !cb) return null;
    const ra = CARDIO_TIER_RANK[ca.tier_word];
    const rb = CARDIO_TIER_RANK[cb.tier_word];
    if (ra == null || rb == null) return null;
    const gap = Math.abs(ra - rb);
    if (gap < 3) return null;
    const better = ra > rb ? a : b;
    const worse  = ra > rb ? b : a;
    return {
      factor: 'cardio',
      delta_pp: -5,
      desc: worse.name + ' fades late vs ' + better.name + "'s output sustain",
    };
  }

  // ROUNDS / TITLE — title fights and 5-round main events tilt toward
  // decisions. The title bump used to be +6 but the 70-80% calibration band
  // ended up worse than coin-flip (research/results.md) — the +6 was pushing
  // fights into the over-confident zone. v2: dropped to +2.
  function roundsFactor(fight) {
    if (fight.is_title_fight) {
      return { factor: 'title', delta_pp: 2, desc: 'title fight (modest distance tilt)' };
    }
    if (fight.is_main_event) {
      return { factor: 'rounds', delta_pp: 2, desc: '5-round main event' };
    }
    return null;
  }

  // FIGHTER FINISH HISTORY — does either fighter have a strong career
  // tendency toward decisions vs finishes? Uses v_fighter_finish_rate
  // (per-fighter career decision_rate / ko_tko_rate / sub_rate over all
  // their UFC fights, both sides). Bayesian-shrunk toward the 0.5 prior
  // so a fighter with 3-and-3 doesn't push the prediction as hard as one
  // with 30-and-30.
  //
  // The factor blends both fighters' shrunken decision rates and converts
  // the deviation from 0.5 into a probability shift. Capped to ±12pp so it
  // can't dominate the prediction by itself.
  function fighterFinishFactor(a, b, finishRateMap) {
    if (!finishRateMap) return null;
    const ra = finishRateMap[a.id];
    const rb = finishRateMap[b.id];
    if (!ra || !rb) return null;
    if (ra.total_fights < 3 || rb.total_fights < 3) return null;
    if (ra.decision_rate == null || rb.decision_rate == null) return null;

    const ALPHA = 5;  // pseudo-count toward 0.5 prior
    const shrunkA = (ra.total_fights * ra.decision_rate + ALPHA * 0.5) / (ra.total_fights + ALPHA);
    const shrunkB = (rb.total_fights * rb.decision_rate + ALPHA * 0.5) / (rb.total_fights + ALPHA);
    const avg = (shrunkA + shrunkB) / 2;

    // Scale: avg of 0.7 → +6pp shift, avg of 0.3 → -6pp shift, capped at ±12.
    let delta_pp = (avg - 0.5) * 30;
    if (delta_pp >  12) delta_pp =  12;
    if (delta_pp < -12) delta_pp = -12;
    if (Math.abs(delta_pp) < 1) return null;

    return {
      factor: 'fighter_history',
      delta_pp,
      desc: 'career decisions: ' + Math.round(shrunkA * 100) + '% / ' + Math.round(shrunkB * 100) + '%',
    };
  }

  function computeDistance(a, b, fight, ctx) {
    ctx = ctx || {};
    const baseRate = baseDistanceRate(fight.weight_class);

    const factors = [
      cardioFactor(a, b, ctx.cardioMap || null, fight.weight_class),
      roundsFactor(fight),
      fighterFinishFactor(a, b, ctx.finishRateMap || null),
    ].filter(Boolean);

    // Additive combination on the probability scale. Each factor's delta_pp
    // is added to the base rate (in points), then clamped to [0.15, 0.85] to
    // prevent the model from claiming near-certainty in either direction.
    let prob = baseRate;
    for (const f of factors) {
      prob += f.delta_pp / 100;
    }
    if (prob > 0.85) prob = 0.85;
    if (prob < 0.15) prob = 0.15;

    return { factors, distanceProb: prob, baseRate };
  }

  const api = {
    DIVISION_DISTANCE_RATE,
    CARDIO_TIER_RANK,
    baseDistanceRate,
    cardioFor,
    cardioFactor,
    roundsFactor,
    fighterFinishFactor,
    computeDistance,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.cflDistanceEdges = api;
  }
})(typeof window !== 'undefined' ? window : this);
