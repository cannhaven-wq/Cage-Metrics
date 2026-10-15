/* ==========================================================================
   Cannon Fight Lab — fight-workspace.js
   The pure rules behind Fight Lab's research workspace: the matchup explorer,
   the "what does this mean" context, and the visitor's own research sheet.
   No network, no DOM, no clock of its own — every function that needs "now"
   takes it — so the browser and tests/fight-workspace.test.js read the same
   rules. The rendering lives in fight-workspace-ui.js.

   Four rules this file holds, so a page cannot quietly drop one:

   1. CAREER AND RECENT ARE DIFFERENT NUMBERS FROM DIFFERENT SOURCES, AND BOTH
      SAY SO. Career rates are UFCStats' career figures off `fighters`. Recent
      rates are recomputed here from `fight_rounds` over the fighter's last
      five completed UFC fights. A recent figure always carries how many of
      those fights had round data and how many minutes it rests on. A fight
      with no round data is left out and named — never filled in.

   2. A DIFFERENCE IS NOT EVIDENCE. Every metric says what it measures. Where
      the Factor Lab (factor-rates.json) has tested whether that kind of gap
      goes with winning once the betting line is controlled for, the result is
      quoted from the artifact with its sample. Where it has not been tested,
      the page says that instead of implying it matters.

   3. NOTHING HERE PICKS A SIDE. No function adds metrics up, weighs them, or
      returns which corner "leads" overall. The explorer reports two numbers
      and their gap; the sheet holds what the VISITOR chose, in the order and
      importance THEY chose. tests/fight-workspace.test.js asserts the summary
      carries no tally.

   4. THE SHEET IS THE VISITOR'S AND STAYS IN THEIR BROWSER. localStorage
      only, per fight, versioned. No account, no table, no network.
   ========================================================================== */
(function () {
  'use strict';

  const RECENT_N = 5;
  const ROUND_MIN = 5;

  // ---- numbers -----------------------------------------------------------
  function n(v) {
    if (v == null || v === '') return null;
    const x = +v;
    return Number.isFinite(x) ? x : null;
  }

  // "4:42" -> 4.7 minutes. Anything else is unknown, not zero.
  function clockMinutes(s) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(s || '').trim());
    if (!m) return null;
    const secs = (+m[1]) * 60 + (+m[2]);
    return secs > 0 && secs <= 300 ? secs / 60 : null;
  }

  // Minutes actually fought: every round before the last is a full five, the
  // last is the clock it ended on. Needs end_round and end_time — a fight
  // without both has an unknown length and is left out of every per-minute
  // rate rather than guessed at.
  function fightMinutes(fight) {
    const r = n(fight && fight.end_round);
    const last = clockMinutes(fight && fight.end_time);
    if (!r || r < 1 || last == null) return null;
    return (r - 1) * ROUND_MIN + last;
  }

  // One fighter's side of one fight, summed over its rounds. Orientation is
  // read off each round row's own fighter_a_id, never assumed from `fights`.
  function sideTotals(rounds, fighterId) {
    const t = { sigL: 0, sigA: 0, oppSigL: 0, oppSigA: 0, tdL: 0, tdA: 0,
                oppTdL: 0, oppTdA: 0, ctrl: 0, kd: 0, sub: 0, rounds: 0 };
    (rounds || []).forEach(r => {
      if (!r) return;
      const me = r.fighter_a_id === fighterId ? 'a' : r.fighter_b_id === fighterId ? 'b' : null;
      if (!me) return;
      const op = me === 'a' ? 'b' : 'a';
      const g = k => n(r[k]) || 0;
      t.sigL += g(me + '_sig_str_landed');  t.sigA += g(me + '_sig_str_attempted');
      t.oppSigL += g(op + '_sig_str_landed'); t.oppSigA += g(op + '_sig_str_attempted');
      t.tdL += g(me + '_td_landed');        t.tdA += g(me + '_td_attempted');
      t.oppTdL += g(op + '_td_landed');     t.oppTdA += g(op + '_td_attempted');
      t.ctrl += g(me + '_ctrl_seconds');
      t.kd += g(me + '_kd');
      t.sub += g(me + '_sub_attempts');
      t.rounds += 1;
    });
    return t;
  }

  function addTotals(x, y) {
    const out = {};
    Object.keys(x).forEach(k => { out[k] = x[k] + (y[k] || 0); });
    return out;
  }

  const ratio = (num, den, k) => den > 0 ? num / den * (k || 1) : null;

  // Per-minute and per-attempt rates in the same units UFCStats uses for the
  // career figures, so the two lines of a metric are comparable.
  function rates(t, minutes) {
    if (!t || !minutes) return null;
    return {
      slpm:    ratio(t.sigL, minutes),
      str_acc: ratio(t.sigL, t.sigA, 100),
      sapm:    ratio(t.oppSigL, minutes),
      str_def: t.oppSigA > 0 ? (1 - t.oppSigL / t.oppSigA) * 100 : null,
      td_avg:  ratio(t.tdL, minutes, 15),
      td_acc:  ratio(t.tdL, t.tdA, 100),
      td_def:  t.oppTdA > 0 ? (1 - t.oppTdL / t.oppTdA) * 100 : null,
      sub_avg: ratio(t.sub, minutes, 15),
      ctrl15:  ratio(t.ctrl / 60, minutes, 15),
      kd15:    ratio(t.kd, minutes, 15),
    };
  }

  // The recent window. `completed` is fight-lab.js::completedFights output
  // (newest first, [{f, e}]); `roundsByFight` maps fight id -> round rows.
  function recentWindow(completed, roundsByFight, fighterId, opts) {
    const N = (opts && opts.n) || RECENT_N;
    const win = (completed || []).slice(0, N);
    const used = [], skipped = [];
    let totals = null, minutes = 0;
    win.forEach(({ f, e }) => {
      const rows = (roundsByFight && roundsByFight[f.id]) || [];
      const mins = fightMinutes(f);
      const isA = f.fighter_a_id === fighterId;
      const base = {
        fightId: f.id, date: e.event_date, eventName: e.name || '',
        opponentId: isA ? f.fighter_b_id : f.fighter_a_id,
        opponentName: (isA ? f.fighter_b_name : f.fighter_a_name) || 'Unknown opponent',
        winnerId: f.winner_id, method: f.method || '',
      };
      if (!rows.length || mins == null) {
        skipped.push(Object.assign(base, { reason: !rows.length ? 'no round data' : 'fight length not recorded' }));
        return;
      }
      const t = sideTotals(rows, fighterId);
      if (!t.rounds) { skipped.push(Object.assign(base, { reason: 'no round data' })); return; }
      used.push(Object.assign(base, { minutes: mins, totals: t, rates: rates(t, mins) }));
      totals = totals ? addTotals(totals, t) : t;
      minutes += mins;
    });
    return {
      window: win.length, used, skipped, minutes,
      totals, rates: totals ? rates(totals, minutes) : null,
    };
  }

  // ---- record-shaped facts ----------------------------------------------
  // All from the same completed-fight list the page's "Last five" uses.
  function isFinish(method) {
    return /^(ko|tko)|^submission/i.test(String(method || '').trim());
  }

  function formFacts(completed, fighterId, today) {
    const list = completed || [];
    const res = list.map(({ f }) => f.winner_id == null ? 'X' : (f.winner_id === fighterId ? 'W' : 'L'));
    const wins = list.filter(({ f }) => f.winner_id === fighterId);
    const finishWins = wins.filter(({ f }) => isFinish(f.method)).length;
    let streak = null;
    if (res.length && res[0] !== 'X') {
      let k = 0; while (k < res.length && res[k] === res[0]) k++;
      streak = { kind: res[0], count: k };
    }
    const last5 = list.slice(0, RECENT_N);
    const lastDate = list.length ? list[0].e.event_date : null;
    return {
      ufcFights: list.length,
      ufcWins: wins.length,
      ufcLosses: res.filter(r => r === 'L').length,
      winPct: list.length ? wins.length / list.length * 100 : null,
      finishWins,
      finishPct: wins.length ? finishWins / wins.length * 100 : null,
      streak,
      daysSinceLast: lastDate && today ? daysBetween(lastDate, today) : null,
      lastDate,
      last5Distance: last5.filter(({ f }) => /^decision/i.test(f.method || '')).length,
      last5Count: last5.length,
    };
  }

  function daysBetween(a, b) {
    const t = s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10));
    return Math.round((t(b) - t(a)) / 86400000);
  }

  // ---- Factor Lab evidence ----------------------------------------------
  // The published artifact is the only source. A factor id that is not in it
  // returns null and the page says "not tested" — it never borrows a nearby
  // factor's result.
  const VERDICT_WORDS = {
    real:         'Holds up when the odds are even',
    lean:         'Can’t tell yet',
    proxy:        'Mostly repeats the betting line',
    inverted:     'Points the wrong way',
    unproven:     'Too few even-odds fights to say',
    insufficient: 'Too few fights to say',
  };

  function evidence(factorRates, factorId) {
    if (!factorRates || !factorId) return null;
    const f = (factorRates.factors || []).find(x => x.id === factorId);
    if (!f) return null;
    const head = f.buckets.find(b => b.headline) || f.buckets[0];
    const floor = factorRates.rules ? factorRates.rules.min_sample : 100;
    const ev = head && head.even;
    const shown = !!(ev && ev.n >= floor);
    let line = 'CFL\u2019s Factor Lab asked: ' + f.question.charAt(0).toLowerCase() + f.question.slice(1) + ' ' +
      (VERDICT_WORDS[head.verdict] || head.verdict) + '. ';
    if (shown) {
      line += 'On ' + ev.n.toLocaleString('en-US') + ' past UFC fights the odds priced as even, it won ' +
        Math.round(ev.pct) + ' out of 100; the likely range is ' + Math.round(ev.ci_lo) + ' to ' +
        Math.round(ev.ci_hi) + '.';
      if (head.verdict === 'real') line += ' That range sits above a coin flip.';
      else if (head.verdict === 'inverted') line += ' That range sits below a coin flip.';
      else line += ' That range includes a coin flip.';
    } else {
      line += 'There are not enough even-odds fights to put a number on it.';
    }
    return {
      id: f.id, label: f.label, verdict: head.verdict,
      verdictWords: VERDICT_WORDS[head.verdict] || head.verdict,
      line, n: ev ? ev.n : 0, note: f.note,
      generatedAt: factorRates.generated_at || null,
    };
  }

  const NOT_TESTED =
    'CFL has not tested whether this predicts winners once the betting line is ' +
    'accounted for. A difference here is a measurement, not evidence that it decides fights.';

  const ONE_FIGHT =
    'Even a result that holds up is measured over hundreds of fights and moves the ' +
    'odds by a few points. It does not tell you how this fight goes.';

  // ---- the metric catalog -------------------------------------------------
  // `career` reads the fighters row; `recent` reads recentWindow().rates.
  // `max` fixes the bar scale per metric, so a bar's length means the same
  // thing whichever two fighters are on the page — scaling to the larger of
  // the pair would make a 0.1 gap look like a chasm.
  const METRICS = {
    striking: [
      { key: 'slpm', label: 'Significant strikes landed a minute', unit: '', dp: 2, max: 8,
        career: 'slpm', recent: 'slpm', factor: 'strike_volume',
        what: 'How many significant strikes (the ones UFCStats counts as meaningful, not pitter-patter) a fighter lands per minute of fighting. It measures volume, not damage.' },
      { key: 'str_acc', label: 'Striking accuracy', unit: '%', dp: 0, max: 100,
        career: 'str_acc', recent: 'str_acc',
        what: 'Of the significant strikes a fighter throws, the share that land.' },
      { key: 'sapm', label: 'Significant strikes absorbed a minute', unit: '', dp: 2, max: 8,
        career: 'sapm', recent: 'sapm',
        what: 'How many significant strikes their opponents land on them per minute. Lower means they get hit less — it also depends on who they fought.' },
      { key: 'str_def', label: 'Striking defence', unit: '%', dp: 0, max: 100,
        career: 'str_def', recent: 'str_def',
        what: 'Of the significant strikes thrown at them, the share that miss.' },
      { key: 'kd15', label: 'Knockdowns per 15 minutes', unit: '', dp: 2, max: 2,
        career: null, recent: 'kd15',
        what: 'Knockdowns scored per 15 minutes of fighting. UFCStats publishes no career figure, so only the recent window is shown. Knockdowns are rare — one more or less moves this a lot.' },
    ],
    grappling: [
      { key: 'td_avg', label: 'Takedowns landed per 15 minutes', unit: '', dp: 2, max: 6,
        career: 'td_avg', recent: 'td_avg',
        what: 'Successful takedowns per 15 minutes of fighting (one three-round fight).' },
      { key: 'td_acc', label: 'Takedown accuracy', unit: '%', dp: 0, max: 100,
        career: 'td_acc', recent: 'td_acc',
        what: 'Of the takedowns a fighter attempts, the share that succeed. A fighter who rarely shoots can read 0% or 100% off a handful of attempts.' },
      { key: 'td_def', label: 'Takedown defence', unit: '%', dp: 0, max: 100,
        career: 'td_def', recent: 'td_def', factor: 'td_def',
        what: 'Of the takedowns opponents attempt on them, the share they stop. Against opponents who never shoot it rests on very few attempts.' },
      { key: 'ctrl15', label: 'Control time per 15 minutes', unit: ' min', dp: 1, max: 10,
        career: null, recent: 'ctrl15',
        what: 'Minutes spent in a controlling position (on top, on the back, pressed against the fence) per 15 minutes of fighting. Only the recent window — UFCStats publishes no career figure.' },
      { key: 'sub_avg', label: 'Submission attempts per 15 minutes', unit: '', dp: 1, max: 3,
        career: 'sub_avg', recent: 'sub_avg',
        what: 'Submission attempts per 15 minutes. An attempt is not a near-finish; UFCStats counts any clear try.' },
    ],
    physical: [
      { key: 'age', label: 'Age', unit: '', dp: 0, max: 45, career: 'age', recent: null, factor: 'age', single: true,
        what: 'Age in years, from the fighter profile in our data.' },
      { key: 'height', label: 'Height', unit: '″', dp: 0, max: 84, career: 'height_in', recent: null, factor: 'height', single: true,
        what: 'Height in inches off the tale of the tape.' },
      { key: 'reach', label: 'Reach', unit: '″', dp: 0, max: 84, career: 'reach_in', recent: null, factor: 'reach', single: true,
        what: 'Arm span in inches off the tale of the tape.' },
    ],
  };

  function fmt(v, m) {
    if (v == null) return null;
    return (+v).toFixed(m.dp) + (m.unit || '');
  }

  // One line of a metric: the two values, the gap in words, nothing else.
  // `hasTapeA/B` false means UFCStats has no UFC fights to rate, so a career
  // rate of 0 is missing data, not a measurement.
  function line(m, va, vb) {
    const a = va == null ? null : +va, b = vb == null ? null : +vb;
    const out = { a, b, aText: fmt(a, m), bText: fmt(b, m), gap: null, gapText: null };
    if (a != null && b != null) {
      out.gap = a - b;
      // A gap between two percentages is in percentage points, not percent.
      const unit = m.unit === '%' ? ' pts' : (m.unit || '');
      out.gapText = Math.abs(out.gap) < Math.pow(10, -m.dp) / 2 ? 'level' : (Math.abs(out.gap)).toFixed(m.dp) + unit;
    }
    return out;
  }

  // ---- the research sheet -------------------------------------------------
  const SHEET_VERSION = 1;
  const IMPORTANCE = [
    { key: 'key',   label: 'Key to my read' },
    { key: 'note',  label: 'Worth noting' },
    { key: 'minor', label: 'Minor' },
  ];

  function sheetKey(fightId) { return 'cfl.sheet.v' + SHEET_VERSION + '.' + fightId; }

  function emptySheet(fightId) {
    return { v: SHEET_VERSION, fightId: String(fightId), items: [], notes: '', updatedAt: null };
  }

  // Anything unreadable is an empty sheet, never an exception.
  function parseSheet(raw, fightId) {
    try {
      const s = JSON.parse(raw);
      if (!s || s.v !== SHEET_VERSION || String(s.fightId) !== String(fightId) || !Array.isArray(s.items)) {
        return emptySheet(fightId);
      }
      s.items = s.items.filter(i => i && typeof i.id === 'string' && typeof i.label === 'string')
        .map(i => Object.assign({ imp: 'note', note: '' }, i));
      s.notes = typeof s.notes === 'string' ? s.notes : '';
      return s;
    } catch (e) { return emptySheet(fightId); }
  }

  function hasItem(sheet, id) { return !!(sheet && sheet.items.some(i => i.id === id)); }

  // Pinning snapshots the values as they read now, with the date, because a
  // price pinned on Tuesday is not the price on Saturday.
  function addItem(sheet, item, nowIso) {
    if (hasItem(sheet, item.id)) return sheet;
    sheet.items.push(Object.assign({ imp: 'note', note: '', pinnedAt: nowIso || null }, item));
    sheet.updatedAt = nowIso || sheet.updatedAt;
    return sheet;
  }

  function removeItem(sheet, id, nowIso) {
    sheet.items = sheet.items.filter(i => i.id !== id);
    sheet.updatedAt = nowIso || sheet.updatedAt;
    return sheet;
  }

  function moveItem(sheet, id, dir) {
    const i = sheet.items.findIndex(x => x.id === id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= sheet.items.length) return sheet;
    const t = sheet.items[i]; sheet.items[i] = sheet.items[j]; sheet.items[j] = t;
    return sheet;
  }

  const SUMMARY_FOOTER =
    'Prepared by you with Cannon Fight Lab. The selections, their importance and the ' +
    'notes are yours. CFL publishes no pick on this fight and does not tell anyone what ' +
    'to bet. Fight statistics are from UFCStats via CFL; market prices are as captured ' +
    'when you added them, not live — check the sportsbook.';

  // Plain text, so it pastes anywhere. Grouped by the visitor's own importance
  // and in their own order. There is deliberately no count, score or tally
  // across items: adding up the rows would be CFL picking a side.
  function summaryText(sheet, ctx) {
    ctx = ctx || {};
    const L = [];
    L.push('RESEARCH SHEET — ' + (ctx.title || 'UFC fight'));
    if (ctx.subtitle) L.push(ctx.subtitle);
    L.push('');
    IMPORTANCE.forEach(level => {
      const items = sheet.items.filter(i => i.imp === level.key);
      if (!items.length) return;
      L.push(level.label.toUpperCase());
      items.forEach(i => {
        L.push('• ' + i.label + (i.scope ? ' (' + i.scope + ')' : ''));
        if (i.a != null || i.b != null) {
          L.push('    ' + (ctx.nameA || 'Corner A') + ': ' + (i.a == null ? 'no data' : i.a) +
                 '   ' + (ctx.nameB || 'Corner B') + ': ' + (i.b == null ? 'no data' : i.b));
        }
        if (i.text) L.push('    ' + i.text);
        const src = [i.source, i.sample].filter(Boolean).join(' · ');
        if (src) L.push('    Source: ' + src);
        if (i.evidence) L.push('    Tested: ' + i.evidence);
        if (i.note && i.note.trim()) L.push('    My note: ' + i.note.trim());
      });
      L.push('');
    });
    if (sheet.notes && sheet.notes.trim()) {
      L.push('MY NOTES');
      sheet.notes.trim().split('\n').forEach(s => L.push(s));
      L.push('');
    }
    if (!sheet.items.length && !(sheet.notes && sheet.notes.trim())) {
      L.push('(Nothing added yet.)');
      L.push('');
    }
    L.push('—');
    L.push(SUMMARY_FOOTER);
    if (ctx.url) L.push(ctx.url);
    return L.join('\n');
  }

  const api = {
    RECENT_N, n, clockMinutes, fightMinutes, sideTotals, rates, recentWindow,
    isFinish, formFacts, daysBetween,
    evidence, VERDICT_WORDS, NOT_TESTED, ONE_FIGHT,
    METRICS, fmt, line,
    SHEET_VERSION, IMPORTANCE, sheetKey, emptySheet, parseSheet, hasItem,
    addItem, removeItem, moveItem, summaryText, SUMMARY_FOOTER,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflWorkspace = api;
})();
