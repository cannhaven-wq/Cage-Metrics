/* ==========================================================================
   Cannon Fight Lab — shared fight-insight helpers
   Single source of truth for the human-readable matchup layer.

   PUBLIC (the research product): buildMatchupNotes + buildMatchupCaveats —
   neutral, measured differences between two fighters, with no pick attached.
   Card Lab, Fight Lab and the event page all read these, so they cannot drift.

   PRIVATE (retained, not rendered on any public surface): buildEdgeBullets +
   buildRedFlags, which phrase the same comparisons around a model pick. The
   model left the public product in September 2026; this code stays because
   the prospective-tracking side still uses that framing and deleting it would
   cost more than keeping it.

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

  // Surname for tight copy. A generational suffix ("Jr.", "III") is not a
  // name — "Michael Aswell Jr." is Aswell, not Jr. — so it is skipped when
  // there is a name in front of it.
  const NAME_SUFFIX = /^(jr\.?|sr\.?|ii|iii|iv|v)$/i;
  function lastName(n) {
    const p = String(n || '').trim().split(/\s+/);
    while (p.length > 1 && NAME_SUFFIX.test(p[p.length - 1])) p.pop();
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
    // What the market says about this pick. marketPct is the vig-free market
    // probability of the PICKED fighter, so:
    //   * below 50, the books favour the opponent — they lean the other way;
    //   * at or above 50 but well under our number, the books agree on the
    //     winner and are much less sure — a gap that wide is more often the
    //     model missing something than the books mispricing it. The market
    //     deserves the presumption of correctness until we have shown
    //     otherwise, and we have not.
    // (This used to test `confidence - marketPct <= -3`, which — because a
    // pick is always above 50 — could only fire when the market was MORE
    // confident in the same fighter, and then said the books leaned the other
    // way. Wrong in every case it fired.)
    if (marketPct != null && marketPct < 50) {
      flags.push(`The books lean the other way — they give ${lastName(opp.name)} about a ${Math.round(100 - marketPct)}% chance, and the market's price is right more often than any model.`);
    } else if (marketPct != null && confidence - marketPct >= 10) {
      flags.push(`The books are much less sure — they give ${lastName(picked.name)} about a ${Math.round(marketPct)}% chance. A gap this wide is more often the model missing something than the market being wrong.`);
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

  // ---------------------------------------------------------------------
  // What these bullets are, and what they are not.
  //
  // The pick and its percentage come from the engine: a gradient-boosted model
  // over 49 point-in-time covariates (cfl_engine/engine.py). NOTHING in this
  // file feeds that model, and the model does not report which of its features
  // moved a given prediction.
  //
  // What buildEdgeBullets and buildRedFlags do is compare the two fighters on
  // the handful of matchup facts a bettor would check by hand -- cardio tier,
  // age, reach, record, takedown defence. They are supporting context, chosen
  // to be readable, and they are true statements about the fighters. They are
  // not a readout of the engine's reasoning, and presenting them as one would
  // be a misrepresentation: a reader would reasonably conclude the model
  // weighed exactly these things, in this order, and it did not.
  //
  // So every surface that renders these lists renders this note with them.
  // It lives here rather than in the pages so the three consumers (index.html,
  // event.html, fighter.html) cannot drift apart on how they describe it --
  // the same reason the bullets themselves live here.
  const CONTEXT_NOTE = 'Matchup context, not the model\u2019s reasoning \u2014 ' +
    'these are the things worth checking by hand. The percentage comes from the ' +
    'engine, which weighs far more than this and does not report which factor ' +
    'moved it.';


  // ---------------------------------------------------------------------
  // NEUTRAL MATCHUP NOTES — the research product's factor layer.
  //
  // buildEdgeBullets above answers "why does the model like this side", which
  // is a question the public product no longer asks. These two answer the
  // question it does ask:
  //
  //     "What are the measurable differences between these two fighters?"
  //
  // Same underlying comparisons, no pick to hang them on. Each note names the
  // corner that holds the measured advantage and states the number behind it.
  // A note is an observation, never a forecast: holding four of these does not
  // make a fighter likely to win, and nothing here is ordered, scored or
  // totalled to suggest that it does.
  //
  // Ordering is by how much the comparison is worth looking at, and that order
  // is Factor Lab-honest: age leads because it is one of only two factors that
  // survive controlling for the betting line, and reach carries its own note
  // saying the opposite (stats.html has the measurements).
  // ---------------------------------------------------------------------

  const MATCHUP_NOTE = 'Measured differences between these two fighters — ' +
    'the things a researcher would check by hand. A measurable advantage is ' +
    'not a forecast, and these are not added up into one.';

  function note(factor, holder, text) { return { factor, holder, text }; }

  function buildMatchupNotes(a, b, ctx) {
    ctx = ctx || {};
    const out = [];
    const baseRates = ctx.baseRates || {};
    const tape = hasTape(a) && hasTape(b);

    // --- Age. The one differential the Factor Lab still finds on fights the
    // market priced as even, so it goes first and carries its base rate.
    if (a.age != null && b.age != null && Math.abs(a.age - b.age) >= 3) {
      const younger = a.age < b.age ? a : b;
      const older   = a.age < b.age ? b : a;
      let suffix = '';
      const br = baseRates.younger;
      if (br && br.younger_winrate != null) {
        suffix = ' — across ' + Number(br.sample_size).toLocaleString() +
                 ' fights on record the younger fighter has won ' +
                 (br.younger_winrate * 100).toFixed(0) + '%';
      }
      out.push(note('age', younger.id,
        lastName(younger.name) + ' is ' + (older.age - younger.age) +
        ' years younger than ' + lastName(older.name) + suffix));
    }

    // --- Cardio tier. Describes how deep a fighter holds his pace, which is
    // a statement about fight LENGTH and not about who wins it.
    const ca = cardioFor(ctx.cardioMap, a.id, ctx.weightClass);
    const cb = cardioFor(ctx.cardioMap, b.id, ctx.weightClass);
    if (ca && cb && ca.tier_word && cb.tier_word) {
      const ra = CARDIO_RANK[ca.tier_word] || 0, rb = CARDIO_RANK[cb.tier_word] || 0;
      if (ra !== rb) {
        const hi = ra > rb ? a : b, lo = ra > rb ? b : a;
        const loWord = ra > rb ? cb.tier_word : ca.tier_word;
        const thin = (ra > rb ? ca : cb).confidence === 'limited' ||
                     (ra > rb ? cb : ca).confidence === 'limited';
        out.push(note('cardio', hi.id,
          lastName(hi.name) + ' holds output deeper into fights; ' +
          lastName(lo.name) + ' ' + loWord + ' late' +
          (thin ? ' (read off a small number of fights)' : '')));
      }
    }

    // --- Grappling: takedown offence against the other corner's defence.
    if (tape && a.td_avg != null && b.td_def != null && a.td_avg >= 2.0 && b.td_def < 65) {
      out.push(note('grappling', a.id,
        lastName(a.name) + ' averages ' + Number(a.td_avg).toFixed(1) +
        ' takedowns a fight into a corner that stops ' + b.td_def + '% of them'));
    }
    if (tape && b.td_avg != null && a.td_def != null && b.td_avg >= 2.0 && a.td_def < 65) {
      out.push(note('grappling', b.id,
        lastName(b.name) + ' averages ' + Number(b.td_avg).toFixed(1) +
        ' takedowns a fight into a corner that stops ' + a.td_def + '% of them'));
    }

    // --- Takedown defence gap.
    if (tape && a.td_def != null && b.td_def != null && Math.abs(a.td_def - b.td_def) >= 8) {
      const hi = a.td_def > b.td_def ? a : b, lo = a.td_def > b.td_def ? b : a;
      out.push(note('td_def', hi.id,
        'Takedown defence: ' + lastName(hi.name) + ' ' + hi.td_def + '%, ' +
        lastName(lo.name) + ' ' + lo.td_def + '%'));
    }

    // --- Striking volume.
    if (tape && a.slpm != null && b.slpm != null && Math.abs(a.slpm - b.slpm) >= 1) {
      const hi = a.slpm > b.slpm ? a : b, lo = a.slpm > b.slpm ? b : a;
      out.push(note('volume', hi.id,
        'Strike volume: ' + lastName(hi.name) + ' lands ' + Number(hi.slpm).toFixed(1) +
        ' a minute, ' + lastName(lo.name) + ' ' + Number(lo.slpm).toFixed(1)));
    }

    // --- Takedown accuracy, only where both corners actually shoot.
    if (tape && a.td_acc != null && b.td_acc != null &&
        (+a.td_avg || 0) > 0 && (+b.td_avg || 0) > 0 && Math.abs(a.td_acc - b.td_acc) >= 12) {
      const hi = a.td_acc > b.td_acc ? a : b, lo = a.td_acc > b.td_acc ? b : a;
      out.push(note('td_acc', hi.id,
        'Takedown accuracy: ' + lastName(hi.name) + ' ' + hi.td_acc + '%, ' +
        lastName(lo.name) + ' ' + lo.td_acc + '%'));
    }

    // --- Reach. Last, and it says out loud that the raw edge does not hold
    // up once the betting line is controlled for. A research product that
    // publishes the measurement has to publish that too.
    if (a.reach_in != null && b.reach_in != null && Math.abs(a.reach_in - b.reach_in) >= 2) {
      const hi = a.reach_in > b.reach_in ? a : b, lo = a.reach_in > b.reach_in ? b : a;
      out.push(note('reach', hi.id,
        lastName(hi.name) + ' is ' + (hi.reach_in - lo.reach_in) +
        '" longer — a raw reach edge does not survive controlling for the ' +
        'betting line, so read it as physical context'));
    }

    return out;
  }

  // What would make every note above less reliable. Missing tape, thin
  // samples, and a market that has barely priced the fight. Shown with the
  // notes, never separately, because a caveat a reader has to go looking for
  // is a caveat that was not made.
  function buildMatchupCaveats(a, b, ctx) {
    ctx = ctx || {};
    const out = [];
    if (!hasTape(a)) out.push(lastName(a.name) + ' has no UFC fights on record — every stat comparison above is thinner than it looks.');
    if (!hasTape(b)) out.push(lastName(b.name) + ' has no UFC fights on record — every stat comparison above is thinner than it looks.');
    const ca = cardioFor(ctx.cardioMap, a.id, ctx.weightClass);
    const cb = cardioFor(ctx.cardioMap, b.id, ctx.weightClass);
    if ((ca && ca.confidence === 'limited') || (cb && cb.confidence === 'limited')) {
      out.push('At least one cardio read here comes from a handful of fights that reached the third round. Treat it as a guess.');
    }
    if (ctx.bookCount != null && ctx.bookCount < 3) {
      out.push('Only ' + ctx.bookCount + ' sportsbook' + (ctx.bookCount === 1 ? ' is' : 's are') +
               ' quoting this fight so far, so the consensus price will move as more arrive.');
    }
    return out;
  }

  const api = { CARDIO_RANK, CONTEXT_NOTE, MATCHUP_NOTE, lastName, cardioFor, hasTape,
                buildEdgeBullets, buildRedFlags, buildMatchupNotes, buildMatchupCaveats };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflInsights = api;
})();
