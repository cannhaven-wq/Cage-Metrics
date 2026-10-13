/* ==========================================================================
   Cannon Fight Lab — fight-lab.js
   The pure helpers behind Fight Lab's "who are these two" and "how do they
   compare" sections: the style label, the last five completed fights, and the
   late-round performance read. No network, no DOM, no clock of its own — every
   function that needs "today" takes it — so the browser and the Node tests
   read exactly the same rules.

   Three rules this file holds, so a page cannot quietly drop one:

   1. THE DIVISION OF THIS BOUT FIRST, CAREER SECOND. Both v_fighter_style and
      v_fighter_consistency emit one row per weight class plus a 'CAREER' row.
      A welterweight bout is read off welterweight fights when there are enough
      of them, and the page says which one it used.

   2. "COMPLETED" MEANS IT HAPPENED. A recent-form list is built from fights
      on a past card with a recorded method. A booked fight, a cancelled bout
      and the fight on this page are never counted as form.

   3. LATE-ROUND OUTPUT IS NOT FATIGUE. The score compares a fighter's output
      in rounds three and later with their own round-one output in the same
      fights. Throwing less late can mean tired, but it can also mean ahead on
      the cards, in top control, hurt, or following a plan. Every label here
      describes output, and the copy that ships with it says so. Our testing
      also found it does not pick winners (CLAUDE.md, cardio section), so it is
      never phrased as an advantage.
   ========================================================================== */
(function () {
  'use strict';

  // ---- scope: this division, else career --------------------------------
  // `has` decides whether a row is usable — a weight-class row can exist with
  // a NULL score when too few fights in that division reached round three.
  function pickScope(rows, fighterId, weightClass, has) {
    const mine = (rows || []).filter(r => r && r.fighter_id === fighterId);
    const ok = has || (() => true);
    if (weightClass) {
      const wc = mine.find(r => r.weight_class === weightClass && ok(r));
      if (wc) return { row: wc, scope: 'division', weightClass };
    }
    const career = mine.find(r => r.weight_class === 'CAREER' && ok(r));
    if (career) return { row: career, scope: 'career', weightClass: null };
    return null;
  }

  // ---- style -------------------------------------------------------------
  const STYLE = {
    striker:  { label: 'Striker',
                line: 'Most of their early output is stand-up striking rather than takedowns and control.' },
    grappler: { label: 'Grappler',
                line: 'Most of their early output is takedowns and control time rather than strikes.' },
    hybrid:   { label: 'Mixes both',
                line: 'Busy on the feet and on the mat — neither side dominates the other.' },
  };

  function styleRead(rows, fighterId, weightClass) {
    const hit = pickScope(rows, fighterId, weightClass, r => !!STYLE[r.style]);
    if (!hit) return null;
    const s = STYLE[hit.row.style];
    const n = hit.row.sample_fights != null ? +hit.row.sample_fights : null;
    return {
      key: hit.row.style,
      label: s.label,
      line: s.line,
      fights: n,
      thin: hit.row.confidence != null && hit.row.confidence !== 'high',
      scope: hit.scope,
      weightClass: hit.weightClass,
    };
  }

  // ---- recent form -------------------------------------------------------
  // `fights` and `events` are raw rows; `today` is 'YYYY-MM-DD'. Newest first.
  function resultFor(fight, fighterId) {
    if (fight.winner_id == null) {
      return /^decision/i.test(fight.method || '') ? 'D' : 'NC';
    }
    return fight.winner_id === fighterId ? 'W' : 'L';
  }

  function shortMethod(m) {
    const s = String(m || '').trim();
    if (!s) return '';
    if (/^decision/i.test(s)) {
      const kind = s.split(/\s*-\s*/)[1] || '';
      return kind ? 'Decision (' + kind.toLowerCase() + ')' : 'Decision';
    }
    if (/^(ko|tko)/i.test(s)) return 'KO/TKO';
    if (/^submission/i.test(s)) return 'Submission';
    if (/^dq|disqualif/i.test(s)) return 'Disqualification';
    if (/overturned|could not continue|no contest/i.test(s)) return s;
    return s;
  }

  function recentForm(fights, events, fighterId, today, opts) {
    opts = opts || {};
    const n = opts.n || 5;
    const exclude = opts.excludeFightId;
    const ev = {};
    (events || []).forEach(e => { if (e) ev[e.id] = e; });
    return (fights || [])
      .filter(f => f && (f.fighter_a_id === fighterId || f.fighter_b_id === fighterId))
      .filter(f => f.id !== exclude)
      .map(f => ({ f, e: ev[f.event_id] }))
      .filter(x => x.e && x.e.event_date && x.e.event_date < today &&
                   x.e.is_upcoming !== true && x.f.method)
      .sort((x, y) => (y.e.event_date.localeCompare(x.e.event_date)) || (y.f.id - x.f.id))
      .slice(0, n)
      .map(({ f, e }) => {
        const isA = f.fighter_a_id === fighterId;
        return {
          fightId: f.id,
          date: e.event_date,
          eventId: e.id,
          eventName: e.name || '',
          opponentId: isA ? f.fighter_b_id : f.fighter_a_id,
          opponentName: (isA ? f.fighter_b_name : f.fighter_a_name) || 'Unknown opponent',
          result: resultFor(f, fighterId),
          method: shortMethod(f.method),
          round: f.end_round || null,
          time: f.end_time || null,
          weightClass: f.weight_class || null,
        };
      });
  }

  // ---- late-round performance -------------------------------------------
  // Keyed on the view's own tier so the bucket edges live in one place (the
  // SQL). Only the words change: none of them says "cardio", "gas" or "tired".
  const LATE = {
    tireless:  { label: 'Busier late',        line: 'Their output in round three and later was higher than in round one.' },
    steady:    { label: 'Kept their pace',    line: 'Their output late in fights stayed close to their round-one level.' },
    tapers:    { label: 'Some drop-off late', line: 'Their output late in fights was noticeably lower than in round one.' },
    fades:     { label: 'Clear drop-off late', line: 'Their output late in fights fell well below their round-one level.' },
    collapses: { label: 'Output more than halved late', line: 'Their output late in fights was less than half their round-one level.' },
  };

  function lateRoundRead(rows, fighterId, weightClass) {
    const hit = pickScope(rows, fighterId, weightClass, r => r.consistency_score != null && LATE[r.cardio_tier]);
    if (!hit) return null;
    const r = hit.row;
    const t = LATE[r.cardio_tier];
    const pace = r.r1_sig_str_per_min != null ? +r.r1_sig_str_per_min : null;
    return {
      tier: r.cardio_tier,
      label: t.label,
      line: t.line,
      keptPct: Math.round(+r.consistency_score),
      fights: r.recent_fights != null ? +r.recent_fights : null,
      lateMinutes: r.r3p_minutes != null ? +r.r3p_minutes : null,
      r1Pace: pace,
      lowPace: pace != null && pace < 4.0,
      thin: r.confidence_tier !== 'high',
      scope: hit.scope,
      weightClass: hit.weightClass,
    };
  }

  const LATE_ROUND_NOTE =
    'This measures output, not tiredness. A fighter can throw less late because they are ' +
    'ahead, holding top position, hurt, or sticking to a plan — and can look busier late ' +
    'because round one was a feeling-out round. It is read only from fights that reached ' +
    'round three, comparing each fighter with their own round-one pace in those same ' +
    'fights. In our testing it says something about how long fights go, and nothing ' +
    'useful about who wins them.';

  const api = { pickScope, styleRead, STYLE, resultFor, shortMethod, recentForm,
                lateRoundRead, LATE, LATE_ROUND_NOTE };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflFightLab = api;
})();
