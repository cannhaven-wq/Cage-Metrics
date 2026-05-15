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
  // go to a decision. Hand-tuned from rough UFC historical norms — replace
  // with live v_finish_rate_by_division values once that's plumbed in.
  const DIVISION_DISTANCE_RATE = {
    'Heavyweight':            0.25,
    'Light Heavyweight':      0.40,
    'Middleweight':           0.45,
    'Welterweight':           0.50,
    'Lightweight':            0.52,
    'Featherweight':          0.58,
    'Bantamweight':           0.62,
    'Flyweight':              0.65,
    'Strawweight':            0.65,
    "Women's Strawweight":    0.78,
    "Women's Flyweight":      0.72,
    "Women's Bantamweight":   0.68,
    "Women's Featherweight":  0.65,
    'Catch Weight':           0.50,
    'Open Weight':            0.30,
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
  // decisions. Title fights more strongly (championship caution: both
  // fighters fight defensively to protect their position).
  function roundsFactor(fight) {
    if (fight.is_title_fight) {
      return { factor: 'title', delta_pp: 6, desc: 'title fight (5 rounds + championship caution)' };
    }
    if (fight.is_main_event) {
      return { factor: 'rounds', delta_pp: 2, desc: '5-round main event' };
    }
    return null;
  }

  function computeDistance(a, b, fight, ctx) {
    ctx = ctx || {};
    const baseRate = baseDistanceRate(fight.weight_class);

    const factors = [
      cardioFactor(a, b, ctx.cardioMap || null, fight.weight_class),
      roundsFactor(fight),
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
    computeDistance,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.cflDistanceEdges = api;
  }
})(typeof window !== 'undefined' ? window : this);
