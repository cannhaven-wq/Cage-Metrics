/* ==========================================================================
   Cannon Fight Lab — shared fight-insight helpers
   Single source of truth for the human-readable "why" behind a pick:
   edge bullets (why the model likes it) and red flags (why it might be
   wrong). Used by index.html and event.html so the two never drift.

   ctx shape (all optional):
     {
       cardioMap:   { [fighter_id]: { byWc: { [weightClass]: {tier_word, confidence} }, career: {...} } },
       weightClass: 'Welterweight' | null,
       baseRates:   { younger: {younger_winrate, sample_size} }
       (age is the only factor whose raw base rate we anchor to — it's the
       only one that survives controlling for the betting line; see stats.html)
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

  // A fighter with no UFC fights has every stat stored as 0, not null. Any
  // comparison against those zeros ("stops more takedowns — 77% to 0%") is a
  // missing-data bug wearing a confident sentence, so stat bullets need real
  // tape on both sides. Age and reach are real regardless.
  function hasTape(f) {
    if (!f) return false;
    if (f.ufc_wins != null || f.ufc_losses != null) {
      return ((+f.ufc_wins || 0) + (+f.ufc_losses || 0) + (+f.ufc_draws || 0)) > 0;
    }
    return !((+f.slpm || 0) === 0 && (+f.sapm || 0) === 0 && (+f.td_def || 0) === 0);
  }

  // Advantages the picked fighter holds, ordered by how much bettors weight
  // them; callers take the top 3. Base-rate anchors are appended when the
  // Stat Finder aggregates are supplied in ctx.
  function buildEdgeBullets(picked, opp, ctx) {
    ctx = ctx || {};
    const out = [];
    const baseRates = ctx.baseRates || {};
    const tape = hasTape(picked) && hasTape(opp);
    // Cardio tier
    const cp = cardioFor(ctx.cardioMap, picked.id, ctx.weightClass);
    const co = cardioFor(ctx.cardioMap, opp.id, ctx.weightClass);
    if (cp && co && cp.tier_word && co.tier_word) {
      const rp = CARDIO_RANK[cp.tier_word] || 0, ro = CARDIO_RANK[co.tier_word] || 0;
      if (rp > ro) {
        const oppWord = co.tier_word;
        out.push((oppWord === 'fades' || oppWord === 'collapses' || oppWord === 'tapers')
          ? `${lastName(picked.name)} lasts deeper into the fight — ${lastName(opp.name)} ${oppWord} late`
          : `${lastName(picked.name)} holds up better in the late rounds`);
      }
    }
    // Takedown defense
    if (tape && picked.td_def != null && opp.td_def != null && picked.td_def - opp.td_def >= 8) {
      out.push(`${lastName(picked.name)} stops more takedowns — ${picked.td_def}% to ${opp.td_def}%`);
    }
    // Grappling offense vs weak defense
    if (tape && picked.td_avg != null && opp.td_def != null && picked.td_avg >= 2.0 && opp.td_def < 65) {
      out.push(`${lastName(picked.name)} can drag it to the mat — ${lastName(opp.name)} stops only ${opp.td_def}% of takedowns`);
    }
    // Age — anchored to the historical base rate when available
    if (picked.age != null && opp.age != null && opp.age - picked.age >= 3) {
      let suffix = '';
      const br = baseRates.younger;
      if (br && br.younger_winrate != null) {
        suffix = ` — the younger fighter wins ${(br.younger_winrate * 100).toFixed(0)}% of ${Number(br.sample_size).toLocaleString()} fights like this`;
      }
      out.push(`${lastName(picked.name)} is ${opp.age - picked.age} years younger${suffix}`);
    }
    // Reach — no win-rate suffix on purpose: the raw historical rate looks
    // predictive but collapses to a coin flip once you control for the
    // betting line (documented in the Factor Lab on stats.html).
    if (picked.reach_in != null && opp.reach_in != null && picked.reach_in - opp.reach_in >= 2) {
      out.push(`${lastName(picked.name)} has ${picked.reach_in - opp.reach_in}" more reach — that range adds up over a fight`);
    }
    // Striking output
    if (tape && picked.slpm != null && opp.slpm != null && (picked.slpm - opp.slpm) >= 1) {
      out.push(`${lastName(picked.name)} lands more — ${Number(picked.slpm).toFixed(1)} clean strikes a minute to ${Number(opp.slpm).toFixed(1)}`);
    }
    // Takedown accuracy
    if (tape && picked.td_acc != null && opp.td_acc != null && (+picked.td_avg || 0) > 0 && (+opp.td_avg || 0) > 0 && picked.td_acc - opp.td_acc >= 12) {
      out.push(`${lastName(picked.name)} hits takedowns more often — ${picked.td_acc}% to ${opp.td_acc}%`);
    }
    return out;
  }

  // The honest counter-case for a pick, ordered by how much each one should
  // worry a bettor; callers take the top 2. Always returns at least one line —
  // pretending certainty is how picks sites lose trust.
  function buildRedFlags(picked, opp, ctx, marketPct, confidence) {
    ctx = ctx || {};
    const flags = [];
    // No UFC tape on one side — say so before anything else
    if (!hasTape(opp)) {
      flags.push(`${lastName(opp.name)} has no UFC fights on record — there's nothing to compare against, so this read is thinner than the number looks.`);
    }
    if (!hasTape(picked)) {
      flags.push(`${lastName(picked.name)} has no UFC fights on record — the model is working off very little tape here.`);
    }
    // The market likes the other guy
    if (marketPct != null && confidence - marketPct <= -3) {
      flags.push(`The books lean the other way — they give ${lastName(opp.name)} about a ${Math.round(100 - marketPct)}% chance, and the market's price is right more often than any model.`);
    }
    // Opponent has the cardio edge
    const cp = cardioFor(ctx.cardioMap, picked.id, ctx.weightClass);
    const co = cardioFor(ctx.cardioMap, opp.id, ctx.weightClass);
    if (cp && co && cp.tier_word && co.tier_word) {
      const rp = CARDIO_RANK[cp.tier_word] || 0, ro = CARDIO_RANK[co.tier_word] || 0;
      if (ro > rp) flags.push(`${lastName(opp.name)} has the better late-round cardio — if this goes long, our pick fades.`);
      else if (cp.confidence === 'limited') flags.push(`${lastName(picked.name)}'s cardio read comes from just a few fights — treat it as a guess, not a fact.`);
    }
    // Giving up youth
    if (picked.age != null && opp.age != null && picked.age - opp.age >= 4) {
      flags.push(`${lastName(picked.name)} is ${picked.age - opp.age} years older — age catches up fast, not slowly.`);
    }
    // Giving up reach
    if (picked.reach_in != null && opp.reach_in != null && opp.reach_in - picked.reach_in >= 3) {
      flags.push(`${lastName(picked.name)} is giving up ${opp.reach_in - picked.reach_in}" of reach — ${lastName(opp.name)} can pick at range all night.`);
    }
    // Thin lean
    if (confidence < 55) {
      flags.push(`This is a lean, not a strong pick — the model barely separates these two.`);
    }
    // Structural flags only. The plain-variance point is made once at the
    // page level (card-lab intro note / edges calibration explainer).
    return flags;
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  const api = { CARDIO_RANK, lastName, cardioFor, hasTape, buildEdgeBullets, buildRedFlags };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflInsights = api;
})();
