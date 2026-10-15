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
                oppTdL: 0, oppTdA: 0, ctrl: 0, kd: 0, sub: 0, rounds: 0,
                head: 0, body: 0, leg: 0, dist: 0, clinch: 0, ground: 0 };
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
      t.head += g(me + '_head_landed');     t.body += g(me + '_body_landed');
      t.leg += g(me + '_leg_landed');
      t.dist += g(me + '_distance_landed'); t.clinch += g(me + '_clinch_landed');
      t.ground += g(me + '_ground_landed');
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
      tdA15:   ratio(t.tdA, minutes, 15),
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


  // Age today and opponent changes are card-level facts shared with Card Lab
  // and the event page; they live in card-research.js.
  const CR = (typeof module !== 'undefined' && module.exports) ? require('./card-research.js') : window.cflCard;
  const ageOn = (dob, today) => CR.ageOn(dob, today);
  const opponentChanges = (cardFights, fight) => CR.opponentChanges(cardFights, fight);

  // ---- every UFC fight, from our own fight rows ---------------------------
  // The UFCStats career figures on `fighters` are only as fresh as the last
  // profile scrape; on 2026-10-15, 68 of 150 fighters on upcoming cards had
  // fought since theirs. `fights` carries the per-fight totals for every UFC
  // bout (complete since 2015 and earlier), so the same rates are rebuilt here
  // from every completed fight in our data. A fight row is shaped like a round
  // row (a_/b_ columns plus fighter ids), so sideTotals reads both.
  function careerWindow(completed, fighterId) {
    const used = [], skipped = [];
    let totals = null, minutes = 0;
    (completed || []).forEach(({ f, e }) => {
      const mins = fightMinutes(f);
      if (mins == null || f.a_sig_str_attempted == null) {
        skipped.push({ fightId: f.id, date: e.event_date, reason: mins == null ? 'fight length not recorded' : 'no fight totals' });
        return;
      }
      const t = sideTotals([f], fighterId);
      if (!t.rounds) return;
      used.push({ fightId: f.id, date: e.event_date, minutes: mins, rates: rates(t, mins), totals: t });
      totals = totals ? addTotals(totals, t) : t;
      minutes += mins;
    });
    return {
      fights: used.length, used, skipped, minutes, totals,
      rates: totals ? rates(totals, minutes) : null,
      first: used.length ? used[used.length - 1].date : null,
      last: used.length ? used[0].date : null,
    };
  }

  // Where the landed significant strikes went. Shares of what landed, so they
  // describe a style, not a volume.
  function strikeMix(t) {
    if (!t) return null;
    const tgt = t.head + t.body + t.leg, pos = t.dist + t.clinch + t.ground;
    const pct = (x, d) => d > 0 ? x / d * 100 : null;
    return {
      landed: tgt,
      target: tgt ? { head: pct(t.head, tgt), body: pct(t.body, tgt), leg: pct(t.leg, tgt) } : null,
      position: pos ? { distance: pct(t.dist, pos), clinch: pct(t.clinch, pos), ground: pct(t.ground, pos) } : null,
    };
  }

  // ---- round by round ------------------------------------------------------
  // Significant strikes landed and absorbed per minute in each round number,
  // over every fight that reached it. The last round of a fight counts only
  // the minutes it lasted, so a 30-second finish does not read as a quiet round.
  function roundByRound(completed, roundsByFight, fighterId) {
    const by = {};
    (completed || []).forEach(({ f }) => {
      const rows = (roundsByFight && roundsByFight[f.id]) || [];
      const endR = n(f.end_round), endClock = clockMinutes(f.end_time);
      if (!rows.length || !endR || endClock == null) return;
      rows.forEach(r => {
        const rn = n(r.round_number);
        if (!rn || rn > endR) return;
        const mins = rn === endR ? endClock : ROUND_MIN;
        const t = sideTotals([r], fighterId);
        if (!t.rounds) return;
        const b = by[rn] || (by[rn] = { round: rn, fights: 0, minutes: 0, landed: 0, absorbed: 0 });
        b.fights += 1; b.minutes += mins; b.landed += t.sigL; b.absorbed += t.oppSigL;
      });
    });
    return Object.keys(by).map(k => by[k]).sort((x, y) => x.round - y.round).map(b => Object.assign(b, {
      landedPm: b.minutes ? b.landed / b.minutes : null,
      absorbedPm: b.minutes ? b.absorbed / b.minutes : null,
    }));
  }

  // ---- how they win and how they lose ------------------------------------
  function methodKind(m) {
    const s = String(m || '').trim();
    if (/^(ko|tko)/i.test(s)) return 'ko';
    if (/^submission/i.test(s)) return 'sub';
    if (/^decision/i.test(s)) return 'dec';
    return 'other';
  }
  function methods(completed, fighterId) {
    const out = { win: { ko: 0, sub: 0, dec: 0, other: 0, total: 0 }, loss: { ko: 0, sub: 0, dec: 0, other: 0, total: 0 } };
    (completed || []).forEach(({ f }) => {
      if (f.winner_id == null) return;
      const side = f.winner_id === fighterId ? out.win : out.loss;
      side[methodKind(f.method)] += 1; side.total += 1;
    });
    return out;
  }

  // ---- quality of opposition ---------------------------------------------
  // Each recent opponent's UFC record going INTO that fight, counted from the
  // same completed-fight rules. A record built afterwards would include the
  // fight being described. `oppCompleted` maps opponent id -> completedFights.
  function recordBefore(completed, fighterId, date) {
    const rec = { w: 0, l: 0, other: 0 };
    (completed || []).forEach(({ f, e }) => {
      if (!(e.event_date < date)) return;
      if (f.winner_id == null) rec.other += 1;
      else if (f.winner_id === fighterId) rec.w += 1;
      else rec.l += 1;
    });
    return rec;
  }
  function opposition(form, oppCompleted) {
    return (form || []).map(r => {
      const list = oppCompleted && oppCompleted[r.opponentId];
      const rec = list ? recordBefore(list, r.opponentId, r.date) : null;
      return Object.assign({}, r, { oppRecord: rec, oppDebut: !!(rec && rec.w + rec.l + rec.other === 0) });
    });
  }

  // ---- division context ----------------------------------------------------
  // LIKE FOR LIKE. Every fighter in the pool — the two on the page included —
  // is reduced to the same measurement: their own bouts in THIS weight class,
  // inside THIS date window, with at least MIN_DIV_MINUTES of fighting. A
  // fighter's rank is the position of that window figure among everyone
  // else's. It is never their all-career figure: that would set a number
  // drawn from other divisions and other years against a three-year,
  // one-division pool. The career figure stays on its own line, separately.
  //
  // `crit` is { weightClass, from, to } ('YYYY-MM-DD', from inclusive, to
  // exclusive). The query asks for the same thing; the rule is enforced here
  // too, so a looser query cannot widen the pool in silence.
  //
  // Weight-class labels do not say men's or women's — "Flyweight" holds both —
  // so the pool is cut to the fighters linked by actual bouts to `anchors` (the
  // two fighters on this page). Men and women never meet, so the link graph
  // separates them without needing a sex field (fighters.sex is almost empty).
  const MIN_DIV_MINUTES = 15;
  const DIV_YEARS = 3;
  const DIV_KEYS = ['slpm', 'str_acc', 'sapm', 'str_def', 'td_avg', 'td_acc', 'td_def', 'sub_avg'];
  const fightDate = f => (f && f.events && f.events.event_date) || (f && f.event_date) || null;
  function inCriteria(f, crit) {
    if (!crit) return true;
    if (crit.weightClass && f.weight_class !== crit.weightClass) return false;
    const d = fightDate(f);
    if ((crit.from || crit.to) && !d) return false;
    if (crit.from && d < crit.from) return false;
    if (crit.to && !(d < crit.to)) return false;
    return true;
  }
  function divisionBaseline(divFights, anchors, crit) {
    const pool = (divFights || []).filter(f => f && f.is_active !== false && inCriteria(f, crit));
    const parent = {};
    const find = x => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
    const join = (x, y) => {
      [x, y].forEach(k => { if (!(k in parent)) parent[k] = k; });
      const rx = find(x), ry = find(y); if (rx !== ry) parent[rx] = ry;
    };
    pool.forEach(f => { if (f.fighter_a_id != null && f.fighter_b_id != null) join(f.fighter_a_id, f.fighter_b_id); });
    const roots = new Set((anchors || []).filter(x => x in parent).map(find));
    const inPool = id => !anchors || !anchors.length || (id in parent && roots.has(find(id)));
    const per = {};
    pool.forEach(f => {
      if (!inPool(f.fighter_a_id)) return;
      const mins = fightMinutes(f);
      if (mins == null || f.a_sig_str_attempted == null) return;
      [f.fighter_a_id, f.fighter_b_id].forEach(id => {
        if (id == null) return;
        const t = sideTotals([f], id);
        const p = per[id] || (per[id] = { t: null, minutes: 0, fights: 0 });
        p.t = p.t ? addTotals(p.t, t) : t; p.minutes += mins; p.fights += 1;
      });
    });
    const out = { fighters: 0, crit: crit || null, byFighter: {} };
    DIV_KEYS.forEach(k => { out[k] = []; });
    Object.keys(per).forEach(id => {
      const p = per[id];
      const r = rates(p.t, p.minutes);
      out.byFighter[id] = { fights: p.fights, minutes: p.minutes, rates: r, counted: p.minutes >= MIN_DIV_MINUTES };
      if (p.minutes < MIN_DIV_MINUTES) return;
      out.fighters += 1;
      DIV_KEYS.forEach(k => { if (r[k] != null) out[k].push(r[k]); });
    });
    DIV_KEYS.forEach(k => out[k].sort((x, y) => x - y));
    return out;
  }

  // One fighter's rank, measured exactly the way the pool was. Returns the
  // window figure that was ranked (so the page can show it), or a reason.
  function divisionRank(base, fighterId) {
    if (!base) return { reason: 'no division data' };
    if (base.fighters < 10) return { reason: 'too few fighters in the pool' };
    const me = base.byFighter[fighterId];
    if (!me) return { reason: 'no bouts in this weight class in the window' };
    if (!me.counted) return { reason: 'under ' + MIN_DIV_MINUTES + ' minutes in this weight class in the window', fights: me.fights, minutes: me.minutes };
    const pct = {};
    DIV_KEYS.forEach(k => { pct[k] = percentile(base[k], me.rates[k]); });
    return { pct, fights: me.fights, minutes: me.minutes, rates: me.rates };
  }

  // The window, as dates: DIV_YEARS back from `today`, today excluded.
  function divisionWindow(weightClass, today) {
    if (!weightClass || !/^\d{4}-\d{2}-\d{2}$/.test(today || '')) return null;
    return { weightClass, from: (+today.slice(0, 4) - DIV_YEARS) + today.slice(4), to: today };
  }
  // Share of the division below v, 0-100. Ties count half, so a value equal to
  // everyone else's reads as the middle rather than the top.
  function percentile(sorted, v) {
    if (!sorted || sorted.length < 10 || v == null) return null;
    let below = 0, eq = 0;
    sorted.forEach(x => { if (x < v) below += 1; else if (x === v) eq += 1; });
    return Math.round((below + eq / 2) / sorted.length * 100);
  }
  // Plain words for a percentile. "Higher" is just higher — absorbed strikes
  // is a metric where a high number is not a compliment, and the words do not
  // pretend otherwise either way.
  function percentileWords(p) {
    if (p == null) return null;
    if (p >= 90) return 'top 10%';
    if (p >= 75) return 'top quarter';
    if (p > 60) return 'above the middle';
    if (p >= 40) return 'around the middle';
    if (p > 25) return 'below the middle';
    if (p > 10) return 'bottom quarter';
    return 'bottom 10%';
  }

  // Weight-class limits in pounds, as the UFC defines them. A fixed fact
  // about the division, not a weigh-in result — CFL does not capture those.
  const WEIGHT_LIMIT = {
    'Strawweight': 115, "Women's Strawweight": 115, 'Flyweight': 125, "Women's Flyweight": 125,
    'Bantamweight': 135, "Women's Bantamweight": 135, 'Featherweight': 145, "Women's Featherweight": 145,
    'Lightweight': 155, 'Welterweight': 170, 'Middleweight': 185, 'Light Heavyweight': 205,
    'Heavyweight': 265,
  };
  function weightLimit(wc) {
    if (!wc) return null;
    const k = String(wc).replace(/\s+Bout$/i, '').replace(/^UFC\s+/i, '').replace(/\s+Title$/i, '').trim();
    return WEIGHT_LIMIT[k] || null;
  }


  // ---- key points: facts, calculations, interpretation ---------------------
  // Three kinds, kept apart because they deserve different amounts of trust:
  //   fact  — read straight off the record (a reach in inches, a result).
  //   calc  — a number CFL computed (a rate, a percentile, a change).
  //   read  — an interpretation: a question the numbers raise. Never a
  //           verdict, never "X wins", never a side. The page says so.
  // `x` is { name, last, age, reach, height, stance, debut, career, recent,
  //          facts, methods, rank, style, late } for each corner, and
  //   ctx is { fight, changes, divisionLabel, windowLabel }.
  function keyPoints(A, B, ctx) {
    ctx = ctx || {};
    const out = [];
    const add = (kind, text, topic) => out.push({ kind, text, topic: topic || null });
    const gap = (va, vb, min, words) => {
      if (va == null || vb == null || Math.abs(va - vb) < min) return;
      const [hi, lo, hv, lv] = va > vb ? [A, B, va, vb] : [B, A, vb, va];
      add('fact', words(hi, lo, hv, lv), 'physical');
    };
    const fight = ctx.fight || {};

    // facts
    if (fight.is_title_fight) add('fact', 'Title fight, scheduled for five rounds.', 'context');
    else if (+fight.scheduled_rounds === 5) add('fact', 'Scheduled for five rounds.', 'context');
    [A, B].forEach(x => { if (x.debut) add('fact', x.last + ' makes a UFC debut: there is no UFC fight data for them.', 'context'); });
    (ctx.changes || []).forEach(c => add('fact', 'Opponent change: ' + c.fighterName + ' was previously booked on this card against ' +
      c.formerOpponent + '; that booking is no longer on the card.', 'context'));
    gap(A.reach, B.reach, 2, (hi, lo, hv, lv) => hi.last + ' has a ' + Math.round(hv - lv) + '-inch reach advantage (' + Math.round(hv) + '″ to ' + Math.round(lv) + '″).');
    gap(A.height, B.height, 2, (hi, lo, hv, lv) => hi.last + ' is ' + Math.round(hv - lv) + ' inches taller (' + Math.round(hv) + '″ to ' + Math.round(lv) + '″).');
    gap(A.age, B.age, 3, (hi, lo, hv, lv) => lo.last + ' is ' + Math.round(hv - lv) + ' years younger (' + lv + ' to ' + hv + ').');
    if (A.stance && B.stance && A.stance !== B.stance && /southpaw/i.test(A.stance + B.stance) && /orthodox/i.test(A.stance + B.stance)) {
      add('fact', 'Southpaw against orthodox: ' + A.last + ' ' + A.stance.toLowerCase() + ', ' + B.last + ' ' + B.stance.toLowerCase() + '.', 'physical');
    }
    [A, B].forEach(x => {
      const m = x.methods;
      if (m && m.win.total >= 3 && m.win.ko / m.win.total >= 0.5) add('fact', x.last + ' has won ' + m.win.ko + ' of ' + m.win.total + ' UFC wins by KO/TKO.', 'form');
      if (m && m.win.total >= 3 && m.win.sub / m.win.total >= 0.4) add('fact', x.last + ' has won ' + m.win.sub + ' of ' + m.win.total + ' UFC wins by submission.', 'form');
      if (m && m.loss.ko >= 2) add('fact', x.last + ' has lost ' + m.loss.ko + ' UFC fights by KO/TKO.', 'form');
      if (m && m.loss.sub >= 2) add('fact', x.last + ' has lost ' + m.loss.sub + ' UFC fights by submission.', 'form');
      const st = x.facts && x.facts.streak;
      if (st && st.count >= 3) add('fact', x.last + (st.kind === 'W' ? ' has won ' : ' has lost ') + st.count + ' UFC fights in a row.', 'form');
      if (x.facts && x.facts.daysSinceLast != null && x.facts.daysSinceLast >= 365) {
        add('fact', x.last + ' has not fought in the UFC for ' + Math.floor(x.facts.daysSinceLast / 30.4) + ' months.', 'form');
      }
    });

    // calculations
    const PCT_LABEL = { slpm: 'significant strikes landed a minute', str_def: 'striking defence',
                        td_avg: 'takedowns landed per 15 minutes', td_def: 'takedown defence',
                        sapm: 'significant strikes absorbed a minute' };
    [A, B].forEach(x => {
      // A rank describes the fighter's figure INSIDE the pool's window — the
      // same bouts, years and weight class as everyone it is ranked against —
      // and the sentence quotes that figure, never the career one.
      const rk = x.rank;
      if (rk && rk.pct && rk.fights >= 3) {
        Object.keys(PCT_LABEL).forEach(k => {
          const p = rk.pct[k], v = rk.rates[k];
          if (p == null || v == null || (p > 20 && p < 80)) return;
          const unitless = k === 'str_def' || k === 'td_def';
          add('calc', x.last + '’s ' + PCT_LABEL[k] + ' in ' + (ctx.windowLabel || 'this weight class') + ' (' +
            (unitless ? Math.round(v) + '%' : v.toFixed(2)) + ', ' + rk.fights + ' fights) is higher than about ' + p + '% of ' +
            (ctx.divisionLabel || 'the division') + ', measured over the same window.', 'rank');
        });
      }
      if (!x.career || !x.career.rates || x.career.fights < 3) return;
      const c = x.career.rates, r = x.recent && x.recent.rates;
      if (r && x.recent.used.length >= 3 && x.career.fights >= x.recent.used.length + 2 && c.slpm > 0 && r.slpm != null) {
        const ch = (r.slpm - c.slpm) / c.slpm;
        if (Math.abs(ch) >= 0.25) add('calc', x.last + ' has landed ' + r.slpm.toFixed(2) + ' significant strikes a minute over the last ' +
          x.recent.used.length + ' fights, ' + (ch > 0 ? 'up' : 'down') + ' from ' + c.slpm.toFixed(2) + ' across all ' + x.career.fights + ' UFC fights.', 'trend');
      }
      if (c && c.slpm != null && c.sapm != null && x.career.fights >= 3) {
        const d = c.slpm - c.sapm;
        if (Math.abs(d) >= 1) add('calc', x.last + ' has ' + (d > 0 ? 'landed ' : 'absorbed ') + Math.abs(d).toFixed(1) +
          ' more significant strikes a minute than ' + (d > 0 ? 'absorbed' : 'landed') + ' across ' + x.career.fights + ' UFC fights.', 'striking');
      }
    });

    // interpretation — questions, not answers
    const sty = x => x.style && x.style.key;
    if ((sty(A) === 'striker' && sty(B) === 'grappler') || (sty(A) === 'grappler' && sty(B) === 'striker')) {
      const g = sty(A) === 'grappler' ? A : B, k = g === A ? B : A;
      add('read', 'Where does this fight happen? In round one of their last ' + RECENT_N + ' fights, ' + g.last +
        '’s output was mostly takedowns and control and ' + k.last + '’s mostly striking. Which of those this fight becomes is a ' +
        'question the numbers can help with, not answer.', 'style');
    }
    [[A, B], [B, A]].forEach(([w, d]) => {
      const tw = w.career && w.career.rates, td = d.career && d.career.rates;
      if (!tw || !td || tw.td_avg == null || td.td_def == null || w.career.fights < 3 || d.career.fights < 3) return;
      if (tw.td_avg >= 1.5) add('read', 'Can ' + w.last + '’s takedowns (' + tw.td_avg.toFixed(1) + ' landed per 15 minutes) get past ' +
        d.last + '’s takedown defence (' + Math.round(td.td_def) + '% stopped)? Both numbers come from different opponents.', 'grappling');
    });
    if (A.late && B.late && A.late.tier && B.late.tier && A.late.tier !== B.late.tier &&
        ((A.late.score >= 100) !== (B.late.score >= 100))) {
      const held = A.late.score >= 100 ? A : B, dropped = held === A ? B : A;
      add('read', 'If it goes past round two: ' + held.last + '’s output has held late in fights and ' + dropped.last +
        '’s has dropped. CFL’s testing found this says more about how long fights go than who wins them.', 'cardio');
    }
    return out;
  }

  const KIND_LABEL = {
    fact: 'Verified fact',
    calc: 'Calculated by CFL',
    read: 'Interpretation',
  };

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
        what: 'Knockdowns scored per 15 minutes of fighting. UFCStats publishes no career figure for this; both lines are CFL\u2019s, from the fight records. Knockdowns are rare — one more or less moves this a lot.' },
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
        what: 'Minutes spent in a controlling position (on top, on the back, pressed against the fence) per 15 minutes of fighting. UFCStats publishes no career figure for this; both lines are CFL\u2019s, from the fight records.' },
      { key: 'tdA15', label: 'Takedown attempts per 15 minutes', unit: '', dp: 2, max: 8,
        career: null, recent: 'tdA15',
        what: 'How often a fighter shoots for a takedown, landed or not, per 15 minutes. It shows how much a fighter wants the fight on the mat, separately from how often they succeed.' },
      { key: 'sub_avg', label: 'Submission attempts per 15 minutes', unit: '', dp: 1, max: 3,
        career: 'sub_avg', recent: 'sub_avg',
        what: 'Submission attempts per 15 minutes. An attempt is not a near-finish; UFCStats counts any clear try.' },
    ],
    physical: [
      { key: 'age', label: 'Age', unit: '', dp: 0, max: 45, career: 'age', recent: null, factor: 'age', single: true, more: ' years older',
        what: 'Age in years, from the fighter profile in our data.' },
      { key: 'height', label: 'Height', unit: '″', dp: 0, max: 84, career: 'height_in', recent: null, factor: 'height', single: true, more: '″ taller', unitless: true,
        what: 'Height in inches off the tale of the tape.' },
      { key: 'reach', label: 'Reach', unit: '″', dp: 0, max: 84, career: 'reach_in', recent: null, factor: 'reach', single: true, more: '″ longer reach', unitless: true,
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
    ageOn, careerWindow, strikeMix, roundByRound, methodKind, methods, recordBefore, opposition,
    MIN_DIV_MINUTES, DIV_YEARS, DIV_KEYS, inCriteria, divisionBaseline, divisionRank, divisionWindow, percentile, percentileWords,
    opponentChanges, WEIGHT_LIMIT, weightLimit, keyPoints, KIND_LABEL,
    isFinish, formFacts, daysBetween,
    evidence, VERDICT_WORDS, NOT_TESTED, ONE_FIGHT,
    METRICS, fmt, line,
    SHEET_VERSION, IMPORTANCE, sheetKey, emptySheet, parseSheet, hasItem,
    addItem, removeItem, moveItem, summaryText, SUMMARY_FOOTER,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflWorkspace = api;
})();
