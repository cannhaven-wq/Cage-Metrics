/* ==========================================================================
   Cannon Fight Lab — shared fight-insight helpers
   Single source of truth for the human-readable "why" behind a pick:
   edge bullets (why the model likes it) and red flags (why it might be
   wrong). Used by index.html and card-lab.html so the two never drift.

   ctx shape (all optional):
     {
       cardioMap:   { [fighter_id]: { byWc: { [weightClass]: {tier_word, confidence} }, career: {...} } },
       weightClass: 'Welterweight' | null,
       baseRates:   { younger: {younger_winrate, sample_size}, reach: {longer_reach_winrate} }
     }
   ========================================================================== */
(function () {
  const CARDIO_RANK = { tireless: 5, steady: 4, tapers: 3, fades: 2, collapses: 1 };

  function lastName(n) {
    const p = String(n || '').trim().split(/\s+/);
    return p[p.length - 1] || n;
  }

  function cardioFor(cardioMap, fighterId, weightClass) {
    if (!cardioMap) return null;
    const slot = cardioMap[fighterId];
    if (!slot) return null;
    if (weightClass && slot.byWc && slot.byWc[weightClass] && slot.byWc[weightClass].tier_word) {
      return Object.assign({}, slot.byWc[weightClass], { source: 'weight_class' });
    }
    if (slot.career && slot.career.tier_word) return Object.assign({}, slot.career, { source: 'career' });
    return null;
  }

  // Advantages the picked fighter holds, ordered by how much bettors weight
  // them; callers take the top 3. Base-rate anchors are appended when the
  // Stat Finder aggregates are supplied in ctx.
  function buildEdgeBullets(picked, opp, ctx) {
    ctx = ctx || {};
    const out = [];
    const baseRates = ctx.baseRates || {};
    // Cardio tier
    const cp = cardioFor(ctx.cardioMap, picked.id, ctx.weightClass);
    const co = cardioFor(ctx.cardioMap, opp.id, ctx.weightClass);
    if (cp && co && cp.tier_word && co.tier_word) {
      const rp = CARDIO_RANK[cp.tier_word] || 0, ro = CARDIO_RANK[co.tier_word] || 0;
      if (rp > ro) {
        const oppWord = co.tier_word;
        out.push((oppWord === 'fades' || oppWord === 'collapses' || oppWord === 'tapers')
          ? `Stronger late-round cardio — ${opp.name} ${oppWord}`
          : 'Stronger late-round cardio score');
      }
    }
    // Takedown defense
    if (picked.td_def != null && opp.td_def != null && picked.td_def - opp.td_def >= 8) {
      out.push(`Stronger takedown defense (${picked.td_def}% vs ${opp.td_def}%)`);
    }
    // Grappling offense vs weak defense
    if (picked.td_avg != null && opp.td_def != null && picked.td_avg >= 2.0 && opp.td_def < 65) {
      out.push(`Grappling edge vs weak takedown defense (${opp.td_def}%)`);
    }
    // Age — anchored to the historical base rate when available
    if (picked.age != null && opp.age != null && opp.age - picked.age >= 3) {
      let suffix = '';
      const br = baseRates.younger;
      if (br && br.younger_winrate != null) {
        suffix = ` — younger fighters win ${(br.younger_winrate * 100).toFixed(0)}% of ${Number(br.sample_size).toLocaleString()} similar fights`;
      }
      out.push(`Younger by ${opp.age - picked.age} years${suffix}`);
    }
    // Reach
    if (picked.reach_in != null && opp.reach_in != null && picked.reach_in - opp.reach_in >= 2) {
      let suffix = '';
      const br = baseRates.reach;
      if (br && br.longer_reach_winrate != null) {
        suffix = ` — longer reach wins ${(br.longer_reach_winrate * 100).toFixed(0)}% historically`;
      }
      out.push(`Reach edge (+${picked.reach_in - opp.reach_in}")${suffix}`);
    }
    // Striking output
    if (picked.slpm != null && opp.slpm != null && (picked.slpm - opp.slpm) >= 1) {
      out.push(`Higher striking output (${Number(picked.slpm).toFixed(1)} vs ${Number(opp.slpm).toFixed(1)}/min)`);
    }
    // Takedown accuracy
    if (picked.td_acc != null && opp.td_acc != null && picked.td_acc - opp.td_acc >= 12) {
      out.push(`Better takedown accuracy (${picked.td_acc}% vs ${opp.td_acc}%)`);
    }
    return out;
  }

  // The honest counter-case for a pick, ordered by how much each one should
  // worry a bettor; callers take the top 2. Always returns at least one line —
  // pretending certainty is how picks sites lose trust.
  function buildRedFlags(picked, opp, ctx, marketPct, confidence) {
    ctx = ctx || {};
    const flags = [];
    // The market likes the other guy
    if (marketPct != null && confidence - marketPct <= -3) {
      flags.push(`The books disagree — the market prices ${lastName(opp.name)} closer to ${Math.round(100 - marketPct)}%, and closing lines are right more often than any public model.`);
    }
    // Opponent has the cardio edge
    const cp = cardioFor(ctx.cardioMap, picked.id, ctx.weightClass);
    const co = cardioFor(ctx.cardioMap, opp.id, ctx.weightClass);
    if (cp && co && cp.tier_word && co.tier_word) {
      const rp = CARDIO_RANK[cp.tier_word] || 0, ro = CARDIO_RANK[co.tier_word] || 0;
      if (ro > rp) flags.push(`${lastName(opp.name)} holds the better late-round cardio score — if this goes long, the pick weakens.`);
      else if (cp.confidence === 'limited') flags.push(`${lastName(picked.name)}'s cardio score is built on a small sample — treat it as a guess, not a fact.`);
    }
    // Giving up youth
    if (picked.age != null && opp.age != null && picked.age - opp.age >= 4) {
      flags.push(`${lastName(picked.name)} is giving up ${picked.age - opp.age} years — age catches up suddenly, not gradually.`);
    }
    // Giving up reach
    if (picked.reach_in != null && opp.reach_in != null && opp.reach_in - picked.reach_in >= 3) {
      flags.push(`Giving up ${opp.reach_in - picked.reach_in}" of reach — ${lastName(opp.name)} can score from range all night.`);
    }
    // Thin lean
    if (confidence < 55) {
      flags.push(`This is a thin lean, not a conviction pick — the model barely separates these two.`);
    }
    // Never pretend certainty
    if (!flags.length) {
      flags.push(`No structural red flag — the main risk is plain variance. Even ${Math.round(confidence)}% picks lose ${Math.round(100 - confidence)} times out of 100.`);
    }
    return flags;
  }

  const api = { CARDIO_RANK, lastName, cardioFor, buildEdgeBullets, buildRedFlags };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflInsights = api;
})();
