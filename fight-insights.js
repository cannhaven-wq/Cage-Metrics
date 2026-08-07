/* ==========================================================================
   Cannon Fight Lab — shared fight-insight helpers
   Single source of truth for the human-readable "why" behind a pick:
   edge bullets (why the model likes it) and red flags (why it might be
   wrong). Used by index.html and card-lab.html so the two never drift.

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
          ? `${lastName(picked.name)} lasts deeper into the fight — ${lastName(opp.name)} ${oppWord} late`
          : `${lastName(picked.name)} holds up better in the late rounds`);
      }
    }
    // Takedown defense
    if (picked.td_def != null && opp.td_def != null && picked.td_def - opp.td_def >= 8) {
      out.push(`${lastName(picked.name)} stops more takedowns — ${picked.td_def}% to ${opp.td_def}%`);
    }
    // Grappling offense vs weak defense
    if (picked.td_avg != null && opp.td_def != null && picked.td_avg >= 2.0 && opp.td_def < 65) {
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
    if (picked.slpm != null && opp.slpm != null && (picked.slpm - opp.slpm) >= 1) {
      out.push(`${lastName(picked.name)} lands more — ${Number(picked.slpm).toFixed(1)} clean strikes a minute to ${Number(opp.slpm).toFixed(1)}`);
    }
    // Takedown accuracy
    if (picked.td_acc != null && opp.td_acc != null && picked.td_acc - opp.td_acc >= 12) {
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

  // Input-weights "box graph" — the transparent, rules-based factors behind a
  // pick (Record / Cardio / Takedown D), each bar sized by its weight. Green
  // when a factor supports the model's pick, amber when it cuts against it.
  // Delegates the math to edges.js (single source of truth). Returns
  // { net, body, hasEdges } HTML strings built on the .wt-* classes — pages
  // supply their own wrapper element and scoped CSS. Null when edges.js isn't
  // loaded or the computation fails.
  function inputWeights(a, b, ctx, pick) {
    ctx = ctx || {};
    const ce = (typeof window !== 'undefined' && window.cflEdges && window.cflEdges.computeEdges) ? window.cflEdges.computeEdges : null;
    if (!ce) return null;
    let v;
    try {
      v = ce(a, b, { cardioMap: ctx.cardioMap, fightWeightClass: ctx.weightClass });
    } catch (e) { return null; }
    const LABEL = { record: 'Record', cardio: 'Cardio', td_def: 'Takedown D' };
    let net;
    if (v.edges.length) {
      const aFav = v.aProb >= 0.5;
      const who = aFav ? a : b;
      const pctNet = Math.round((aFav ? v.aProb : 1 - v.aProb) * 100);
      net = `Model leans ${esc(lastName(who.name))} — ${pctNet}%`;
    } else {
      net = 'No clear edge';
    }
    const rows = v.edges.map(e => {
      const fav = e.favors === 'a' ? a : b;
      const supports = pick && fav.id === pick.picked.id;
      const cls = pick ? (supports ? 'support' : 'against') : '';
      const w = Math.max(6, Math.min(100, ((e.pct - 50) / 22) * 100));
      return `<div class="wt-row ${cls}">
        <div class="wt-label">${LABEL[e.factor] || esc(e.factor)}</div>
        <div class="wt-track"><i style="width:${w.toFixed(0)}%"></i></div>
        <div class="wt-pct">${e.pct.toFixed(0)}% ${esc(lastName(fav.name))}</div>
      </div>`;
    }).join('');
    const body = v.edges.length
      ? `<div class="wt-note">The clear-cut factors behind this pick — the same ones the model weighs. Green backs the pick, amber works against it.</div><div class="wt-rows">${rows}</div>`
      : `<div class="wt-empty">No clear edge on record, cardio, or takedown defense here — the pick rests on the model's wider read.</div>`;
    return { net, body, hasEdges: v.edges.length > 0 };
  }

  const api = { CARDIO_RANK, lastName, cardioFor, buildEdgeBullets, buildRedFlags, inputWeights };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflInsights = api;
})();
