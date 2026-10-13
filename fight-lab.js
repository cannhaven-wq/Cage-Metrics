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

   2. "COMPLETED" MEANS IT HAPPENED. A fight counts only if it is an active
      booking (`is_active` is not false) on a past card with a recorded
      method. A retired or cancelled booking never counts, even if a method
      was somehow written to it; neither does a booked fight or the fight on
      this page. The UFC record shown beside the list is counted from the SAME
      list, so the two can never disagree. `fighters.ufc_wins/ufc_losses` is
      not shown: it lags `fights` (T-083), and a record that contradicts the
      fight history printed under it is worse than no record.

   3. LATE-ROUND OUTPUT IS NOT FATIGUE, AND IT IS A SCORE, NOT A PERCENTAGE.
      v_fighter_consistency blends up to four late-vs-round-one ratios
      (significant strikes thrown, significant strikes landed, total strikes
      thrown, and takedowns-plus-control for fighters who grapple early),
      weights each by the fighter's own round-one rate, and caps each at 1.15
      to 1.5 depending on how many late minutes there are. 100 means the pace
      was held. It is never printed with a % sign. Throwing less late can mean
      tired, but it can also mean ahead on the cards, in top control, hurt, or
      following a plan. Our testing found it does not pick winners (CLAUDE.md,
      cardio section), so it is never phrased as an advantage.
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

  // Did this booking actually happen? `e` is its event row; `today` is the
  // viewer's 'YYYY-MM-DD'. A card dated today has not finished.
  function isCompleted(f, e, today) {
    return !!(f && e && e.event_date && e.event_date < today &&
              e.is_upcoming !== true &&
              f.is_active !== false &&
              typeof f.method === 'string' && f.method.trim() !== '');
  }

  // Every completed UFC fight for one fighter, newest first.
  function completedFights(fights, events, fighterId, today, opts) {
    opts = opts || {};
    const exclude = opts.excludeFightId;
    const ev = {};
    (events || []).forEach(e => { if (e) ev[e.id] = e; });
    return (fights || [])
      .filter(f => f && (f.fighter_a_id === fighterId || f.fighter_b_id === fighterId))
      .filter(f => f.id !== exclude)
      .map(f => ({ f, e: ev[f.event_id] }))
      .filter(x => isCompleted(x.f, x.e, today))
      .sort((x, y) => (y.e.event_date.localeCompare(x.e.event_date)) || (y.f.id - x.f.id));
  }

  function recentForm(fights, events, fighterId, today, opts) {
    opts = opts || {};
    const n = opts.n || 5;
    return completedFights(fights, events, fighterId, today, opts)
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

  // The UFC record, counted from the same completed fights the page lists.
  function ufcRecord(fights, events, fighterId, today, opts) {
    const rec = { w: 0, l: 0, d: 0, nc: 0, total: 0 };
    completedFights(fights, events, fighterId, today, opts).forEach(({ f }) => {
      const r = resultFor(f, fighterId);
      rec[{ W: 'w', L: 'l', D: 'd', NC: 'nc' }[r]] += 1;
      rec.total += 1;
    });
    return rec;
  }

  function formatUfcRecord(rec) {
    if (!rec || !rec.total) return 'No UFC fights';
    return rec.w + '-' + rec.l + (rec.d ? '-' + rec.d : '') + (rec.nc ? ' (' + rec.nc + ' NC)' : '');
  }

  // The professional record comes from `fighters` and includes other
  // promotions, so it is normally larger than the UFC one. If the UFC count
  // ever exceeds it on wins or losses, the pro total is provably behind.
  function proRecordIsBehind(fighter, rec) {
    if (!fighter || !rec) return false;
    const w = fighter.wins, l = fighter.losses;
    return (w != null && rec.w > +w) || (l != null && rec.l > +l);
  }

  // ---- late-round performance -------------------------------------------
  // Keyed on the view's own tier so the bucket edges live in one place (the
  // SQL). Only the words change: none of them says "cardio", "gas" or "tired".
  const LATE = {
    tireless:  { label: 'Busier late',         line: 'On this score their output in round three and later came out above their round-one level.' },
    steady:    { label: 'Kept their pace',     line: 'On this score their output late in fights stayed close to their round-one level.' },
    tapers:    { label: 'Some drop-off late',  line: 'On this score their output late in fights came out noticeably below their round-one level.' },
    fades:     { label: 'Clear drop-off late', line: 'On this score their output late in fights came out well below their round-one level.' },
    collapses: { label: 'Big drop-off late',   line: 'On this score their output late in fights came out at less than half their round-one level.' },
  };

  // The view's own thresholds (v_fighter_consistency.sql). tests/fight-lab.test.js
  // reads the SQL and fails if these drift from it.
  const SOLID_LATE_MINUTES = 15;   // confidence_tier 'high' needs r3p_minutes >= 15
  const SOLID_R1_MINUTES = 8;      // ...and r1_minutes >= 8
  const MIN_LATE_MINUTES = 10;     // below this no ratio is computed at all
  const SCORE_CAP_MIN = 115;       // dim_cap 1.15 with under 15 late minutes
  const SCORE_CAP_MAX = 150;       // dim_cap 1.5 with 60+ late minutes

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
      score: Math.round(+r.consistency_score),
      fights: r.recent_fights != null ? +r.recent_fights : null,
      lateMinutes: r.r3p_minutes != null ? +r.r3p_minutes : null,
      r1Minutes: r.r1_minutes != null ? +r.r1_minutes : null,
      r1Pace: pace,
      lowPace: pace != null && pace < 4.0,
      thin: r.confidence_tier !== 'high',
      scope: hit.scope,
      weightClass: hit.weightClass,
    };
  }

  const LATE_ROUND_NOTE =
    'This is a score, not a measurement of tiredness. For each fighter it compares output in ' +
    'round three and later with their own round one, in the same fights: significant strikes ' +
    'thrown, significant strikes landed and total strikes thrown, plus takedowns and control time ' +
    'for fighters who wrestle early. Each comparison is weighted by how much of that the fighter ' +
    'does in round one, and capped — at ' + SCORE_CAP_MIN + ' with little late-round fighting, ' +
    'rising to ' + SCORE_CAP_MAX + ' with a lot — so a short sample cannot produce an extreme ' +
    'score. 100 means they kept their round-one pace. Throwing less late can mean tired, but ' +
    'also ahead, holding top position, hurt or sticking to a plan. In our testing it says ' +
    'something about how long fights go, and nothing useful about who wins them.';

  const SOLID_SAMPLE_NOTE =
    '"Solid" means at least ' + SOLID_LATE_MINUTES + ' minutes of fighting in round three or ' +
    'later and at least ' + SOLID_R1_MINUTES + ' round-one minutes from the same fights; ' +
    'anything less is "thin". With under ' + MIN_LATE_MINUTES + ' late-round minutes there is ' +
    'no score at all.';

  const api = { pickScope, styleRead, STYLE, resultFor, shortMethod,
                isCompleted, completedFights, recentForm, ufcRecord, formatUfcRecord,
                proRecordIsBehind, lateRoundRead, LATE, LATE_ROUND_NOTE, SOLID_SAMPLE_NOTE,
                SOLID_LATE_MINUTES, SOLID_R1_MINUTES, MIN_LATE_MINUTES, SCORE_CAP_MIN, SCORE_CAP_MAX };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflFightLab = api;
})();
