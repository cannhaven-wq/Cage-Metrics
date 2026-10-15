/* ==========================================================================
   Cannon Fight Lab — fight-workspace-ui.js
   The research workspace on fight.html: the matchup explorer (six tabs of
   side-by-side bars), the "what this means" context under every metric, and
   the visitor's own research sheet. Rules live in fight-workspace.js; this
   file only draws them and remembers what the visitor pinned.

   What it must never do: add rows up, colour a corner as "ahead", or put a
   pick, a probability of CFL's own or a stake anywhere. Corner colours mark
   WHICH fighter a bar belongs to, nothing more.
   ========================================================================== */
(function () {
  'use strict';

  const W = window.cflWorkspace;
  const FL = window.cflFightLab;
  const M = window.cflMarket;
  const esc = s => window.cfl.escapeHtml(s == null ? '' : String(s));

  let C = null;            // the page context handed to mount()
  let sheet = null;        // the visitor's sheet for this fight
  const registry = {};     // pin id -> item, for buttons drawn anywhere on the page
  let activeTab = 'key';

  // ---- storage: this browser only ----------------------------------------
  function loadSheet(fightId) {
    let raw = null;
    try { raw = window.localStorage.getItem(W.sheetKey(fightId)); } catch (e) {}
    return raw ? W.parseSheet(raw, fightId) : W.emptySheet(fightId);
  }
  let storageOk = true;
  function saveSheet() {
    try {
      window.localStorage.setItem(W.sheetKey(sheet.fightId), JSON.stringify(sheet));
      storageOk = true;
    } catch (e) { storageOk = false; }
  }

  const nowIso = () => new Date().toISOString();
  const last = n => (window.cflInsights ? window.cflInsights.lastName(n) : n);

  // ---- small drawing helpers ---------------------------------------------
  function bfly(m, ln) {
    const w = v => v == null ? 0 : Math.max(0, Math.min(100, (+v) / m.max * 100));
    const val = (t, side) => t == null
      ? '<span class="ws-v na">' + (side.noTape ? 'no UFC data' : 'no data') + '</span>'
      : '<span class="ws-v">' + esc(t) + '</span>';
    return '<div class="ws-bfly">' +
      val(ln.aText, { noTape: ln.noTapeA }) +
      '<span class="ws-bar a"><i style="width:' + w(ln.a).toFixed(1) + '%"></i></span>' +
      '<span class="ws-axis" aria-hidden="true"></span>' +
      '<span class="ws-bar b"><i style="width:' + w(ln.b).toFixed(1) + '%"></i></span>' +
      val(ln.bText, { noTape: ln.noTapeB }) +
    '</div>';
  }

  function gapWords(m, ln) {
    if (ln.gap == null) return null;
    if (ln.gapText === 'level') return 'level';
    if (m.more) return last(ln.gap > 0 ? C.a.name : C.b.name) + ' ' + Math.abs(ln.gap).toFixed(m.dp) + m.more;
    return last(ln.gap > 0 ? C.a.name : C.b.name) + ' ' + ln.gapText + ' higher';
  }

  function tested(ev) {
    if (!ev) return '<span class="ws-tag untested">Not tested as a predictor</span>';
    return '<span class="ws-tag v-' + esc(ev.verdict) + '">Tested: ' + esc(ev.verdictWords) + '</span>';
  }

  function pinBtn(item) {
    registry[item.id] = item;
    const on = W.hasItem(sheet, item.id);
    return '<button type="button" class="ws-pin' + (on ? ' on' : '') + '" data-pin="' + esc(item.id) +
      '" aria-pressed="' + on + '">' + (on ? '✓ On my sheet' : '+ Add to my sheet') + '</button>';
  }

  function ctxBtn(id) {
    return '<button type="button" class="ws-more" aria-expanded="false" aria-controls="' + id + '">What this means</button>';
  }

  // Factor Lab coverage: the test only scores fighters with enough prior UFC
  // fights. If this matchup falls outside that, say so beside the result.
  function coverage(factorId) {
    const R = C.factorRates && C.factorRates.rules;
    if (!R) return '';
    const need = factorId === 'ufc_record' ? R.min_record_fights
      : ['strike_volume', 'td_def', 'finish_rate'].indexOf(factorId) >= 0 ? R.min_prior_fights : null;
    if (!need) return '';
    const short = [[C.a, C.factsA], [C.b, C.factsB]].filter(([, f]) => f && f.ufcFights < need);
    if (!short.length) return '';
    return ' The test only scores fighters with at least ' + need + ' prior UFC fights; ' +
      short.map(([p, f]) => last(p.name) + ' has ' + f.ufcFights).join(' and ') +
      ', so it does not cover this matchup.';
  }

  function evidenceBlock(ev, factorId, custom) {
    if (custom) return '<p class="ws-ev"><b>Does it predict winners?</b> ' + esc(custom) + '</p>';
    if (!ev) return '<p class="ws-ev"><b>Does it predict winners?</b> ' + esc(W.NOT_TESTED) + '</p>';
    return '<p class="ws-ev"><b>Does it predict winners?</b> ' + esc(ev.line) +
      esc(coverage(factorId)) + ' ' + esc(W.ONE_FIGHT) +
      ' <a href="stats.html">See the full test in the Factor Lab</a>.</p>';
  }

  function recentSample(rw) {
    if (!rw) return 'round data could not be loaded';
    if (!rw.window) return 'no completed UFC fights';
    let s = rw.used.length + ' of last ' + rw.window + ' fight' + (rw.window === 1 ? '' : 's') +
      ', ' + Math.round(rw.minutes) + ' min';
    if (rw.skipped.length) s += ' (' + rw.skipped.length + ' left out: ' + rw.skipped[0].reason + ')';
    return s;
  }

  // "May 2026" — a five-fight window spans years, so the year matters more than the day.
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function monthYear(d) {
    const m = /^(\d{4})-(\d{2})/.exec(d || '');
    return m ? MONTHS[+m[2] - 1] + ' ' + m[1] : (d || '');
  }

  function careerSample(cw) {
    if (!cw) return 'fight records could not be loaded';
    if (!cw.fights) return 'no UFC fights with stats';
    return cw.fights + ' UFC fight' + (cw.fights === 1 ? '' : 's') + ', ' + Math.round(cw.minutes) + ' min' +
      (cw.skipped.length ? ' (' + cw.skipped.length + ' left out: ' + cw.skipped[0].reason + ')' : '');
  }

  // Division rank for one metric, like for like: the figure each fighter is
  // ranked on is their own bouts inside the pool's window (same weight class,
  // same years, same minimum minutes) — shown beside the rank, because it is
  // not the all-UFC figure above it. null when neither corner has a rank row.
  function rankRow(m) {
    const ra = C.rankA, rb = C.rankB;
    if (!ra && !rb) return null;
    const has = r => r && r.pct && r.pct[m.recent] != null;
    if (!has(ra) && !has(rb) && !(ra && ra.reason) && !(rb && rb.reason)) return null;
    const one = (p, r) => {
      if (has(r)) return last(p.name) + ' ' + W.fmt(r.rates[m.recent], m) + ' in ' + r.fights + ' fight' + (r.fights === 1 ? '' : 's') +
        ' — higher than ' + r.pct[m.recent] + '%';
      return last(p.name) + ' not ranked (' + ((r && r.reason) || 'no figure') + ')';
    };
    return 'Division rank, ' + (C.windowLabel || 'this weight class') + ': ' + one(C.a, ra) + ' · ' + one(C.b, rb);
  }

  // The scraped UFCStats career figure, kept for reference with its age.
  function profileNote(m) {
    const one = (p, cw) => {
      const v = W.n(p[m.career]);
      if (v == null) return last(p.name) + ': none';
      const upd = p.updated_at ? String(p.updated_at).slice(0, 10) : null;
      const since = upd && cw ? cw.used.filter(u => u.date > upd).length : 0;
      return last(p.name) + ' ' + W.fmt(v, m) + (upd ? ' (profile refreshed ' + monthYear(upd) +
        (since ? '; ' + since + ' UFC fight' + (since === 1 ? '' : 's') + ' since, not included' : '') + ')' : '');
    };
    return '<p class="ws-fine"><b>UFCStats profile figure.</b> ' + esc(one(C.a, C.careerA)) + ' · ' + esc(one(C.b, C.careerB)) +
      '. CFL\u2019s "All UFC fights" line is rebuilt from the fight records, so it includes fights a stale profile misses.</p>';
  }

  // The fight-by-fight numbers behind a "last 5" figure.
  function history(m) {
    if (!m.recent) return '';
    const col = (p, rw) => {
      if (!rw || !rw.window) return '<div class="ws-hcol"><div class="ws-hhd">' + esc(p.name) + '</div><div class="ws-hnone">No completed UFC fights.</div></div>';
      const rows = rw.used.map(u => {
        const v = u.rates ? u.rates[m.recent] : null;
        const res = u.winnerId == null ? 'NC/D' : (u.winnerId === p.id ? 'W' : 'L');
        return '<tr><td>' + esc(monthYear(u.date)) + '</td>' +
          '<td>' + esc(res) + ' vs ' + esc(u.opponentName) + '</td>' +
          '<td class="n">' + (v == null ? '—' : esc(W.fmt(v, m))) + '</td>' +
          '<td class="n">' + esc(u.minutes.toFixed(1)) + '</td></tr>';
      }).join('') + rw.skipped.map(s =>
        '<tr class="skip"><td>' + esc(monthYear(s.date)) + '</td>' +
        '<td>vs ' + esc(s.opponentName) + '</td><td class="n" colspan="2">' + esc(s.reason) + '</td></tr>').join('');
      return '<div class="ws-hcol"><div class="ws-hhd">' + esc(p.name) + '</div>' +
        '<table class="ws-htab"><thead><tr><th>Date</th><th>Fight</th><th class="n">' + esc(m.unit.trim() || 'Value') +
        '</th><th class="n">Min</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
    };
    return '<div class="ws-hist"><div class="ws-k">Fight by fight, last ' + W.RECENT_N + '</div>' +
      '<div class="ws-hgrid">' + col(C.a, C.recentA) + col(C.b, C.recentB) + '</div>' +
      '<div class="ws-fine">One fight can swing a five-fight figure a long way — read the rows, not just the total. ' +
      'Who they fought is not adjusted for.</div></div>';
  }

  // ---- one statistical metric (striking, grappling, physical) ------------
  function metricCard(cat, m) {
    const tapeA = window.cflInsights ? window.cflInsights.hasTape(C.a) : true;
    const tapeB = window.cflInsights ? window.cflInsights.hasTape(C.b) : true;
    const lines = [];
    if (m.single) {
      const ln = W.line(m, W.n(C.a[m.career]), W.n(C.b[m.career]));
      lines.push({ scope: 'Tale of the tape', ln, sample: m.key === 'age' ? 'computed from date of birth where we hold one' : 'fighter profile' });
    } else {
      // "All UFC fights" is CFL's own figure from every completed UFC fight in
      // our data, so it includes fights the scraped profile has not caught up
      // with. The UFCStats profile figure is kept for reference in the context.
      const ca = C.careerA && C.careerA.rates, cb = C.careerB && C.careerB.rates;
      const ln = W.line(m, ca ? ca[m.recent] : null, cb ? cb[m.recent] : null);
      ln.noTapeA = !(C.careerA && C.careerA.fights); ln.noTapeB = !(C.careerB && C.careerB.fights);
      const thin = [[C.a, C.careerA], [C.b, C.careerB]].filter(([, cw]) => cw && cw.fights > 0 && cw.fights < 3)
        .map(([p, cw]) => last(p.name) + ' ' + cw.fights + ' UFC fight' + (cw.fights === 1 ? '' : 's'));
      lines.push({ scope: 'All UFC fights', ln, thin: thin.length ? 'Small sample: ' + thin.join(', ') + ' — treat as a rough guide' : null,
        sample: last(C.a.name) + ': ' + careerSample(C.careerA) + ' · ' + last(C.b.name) + ': ' + careerSample(C.careerB) });
    }
    if (m.recent) {
      const ra = C.recentA && C.recentA.rates, rb = C.recentB && C.recentB.rates;
      const ln = W.line(m, ra ? ra[m.recent] : null, rb ? rb[m.recent] : null);
      lines.push({ scope: 'Last ' + W.RECENT_N, ln,
        sample: last(C.a.name) + ': ' + recentSample(C.recentA) + ' · ' + last(C.b.name) + ': ' + recentSample(C.recentB) });
    }
    const ev = m.factor ? W.evidence(C.factorRates, m.factor) : null;
    const id = 'wsx-' + m.key;
    const rank = m.single ? null : rankRow(m);
    const gaps = lines.map(l => { const g = gapWords(m, l.ln); return g ? l.scope + ': ' + g : null; }).filter(Boolean);

    const item = {
      id: 'm:' + m.key, cat, label: m.label,
      a: lines.map(l => (l.ln.aText || 'no data') + (m.single ? '' : ' ' + l.scope.toLowerCase())).join(' · '),
      b: lines.map(l => (l.ln.bText || 'no data') + (m.single ? '' : ' ' + l.scope.toLowerCase())).join(' · '),
      source: m.single ? 'Fighter profile' : 'CFL, from every UFC fight in our data + the last ' + W.RECENT_N,
      sample: rank,
      evidence: ev ? ev.verdictWords + ' (Factor Lab, ' + ev.n + ' even-odds fights)' : 'Not tested as a predictor',
    };

    return '<article class="ws-m">' +
      '<header class="ws-mh"><h4>' + esc(m.label) + '</h4>' + tested(ev) + '</header>' +
      lines.map(l => '<div class="ws-line"><span class="ws-scope">' + esc(l.scope) + '</span>' + bfly(m, l.ln) +
        (l.thin ? '<div class="ws-rank thin">' + esc(l.thin) + '</div>' : '') + '</div>').join('') +
      (rank ? '<div class="ws-rank ws-rankrow">' + esc(rank) + '</div>' : '') +
      '<div class="ws-gap">' + (gaps.length ? 'Measured difference — ' + esc(gaps.join(' · ')) : 'No difference can be measured: a figure is missing.') + '</div>' +
      '<div class="ws-acts">' + ctxBtn(id) + pinBtn(item) + '</div>' +
      '<div class="ws-ctx" id="' + id + '" hidden>' +
        '<p><b>What it measures.</b> ' + esc(m.what) + '</p>' +
        evidenceBlock(ev, m.factor) +
        '<p class="ws-fine"><b>Sample.</b> ' + lines.map(l => esc(l.scope) + ': ' + esc(l.sample)).join('<br>') + '</p>' +
        (rank ? '<p class="ws-fine"><b>Division rank.</b> ' + esc(C.divNote || '') + '</p>' : '') +
        (m.career && !m.single ? profileNote(m) : '') +
        history(m) +
      '</div>' +
    '</article>';
  }

  // ---- cardio ---------------------------------------------------------------
  function cardioTab() {
    const wc = C.fight.weight_class || null;
    const ra = FL.lateRoundRead(C.consRows, C.a.id, wc);
    const rb = FL.lateRoundRead(C.consRows, C.b.id, wc);
    const m = { key: 'late', label: 'Late-round pace score', unit: '', dp: 0, max: 150 };
    const ln = W.line(m, ra ? ra.score : null, rb ? rb.score : null);
    const samp = (p, r) => r
      ? last(p.name) + ': ' + (r.fights != null ? r.fights + ' fights reached round 3, ' : '') +
        (r.lateMinutes != null ? Math.round(r.lateMinutes) + ' late-round minutes, ' : '') +
        (r.thin ? 'thin sample' : 'solid sample') + ', ' + (r.scope === 'division' ? 'at ' + r.weightClass : 'all divisions')
      : last(p.name) + ': not enough late-round fighting to score';
    const custom = 'In CFL’s testing this score says something about how long fights go and nothing useful ' +
      'about who wins them, so it is not offered as a reason to back either fighter.';
    const lateItem = {
      id: 'm:late', cat: 'cardio', label: 'Late-round pace score (100 = kept round-one pace)',
      a: ra ? ra.score + ' — ' + ra.label : 'not scored', b: rb ? rb.score + ' — ' + rb.label : 'not scored',
      source: 'CFL late-round score (v_fighter_consistency)', sample: [samp(C.a, ra), samp(C.b, rb)].join(' · '),
      evidence: 'Not a predictor of who wins in CFL testing',
    };
    const lenM = { key: 'len', label: 'Average fight length, last ' + W.RECENT_N, unit: ' min', dp: 1, max: 25 };
    const avg = rw => rw && rw.used.length ? rw.minutes / rw.used.length : null;
    const lenLn = W.line(lenM, avg(C.recentA), avg(C.recentB));
    const distA = C.factsA, distB = C.factsB;
    const lenItem = {
      id: 'm:len', cat: 'cardio', label: lenM.label,
      a: lenLn.aText || 'no data', b: lenLn.bText || 'no data', source: 'CFL round data',
      sample: last(C.a.name) + ': ' + recentSample(C.recentA) + ' · ' + last(C.b.name) + ': ' + recentSample(C.recentB),
    };
    const decItem = {
      id: 'm:dist', cat: 'cardio', label: 'Went the distance, last ' + W.RECENT_N,
      a: distA ? distA.last5Distance + ' of ' + distA.last5Count : 'no data',
      b: distB ? distB.last5Distance + ' of ' + distB.last5Count : 'no data',
      source: 'Completed UFC fights',
    };
    return '<article class="ws-m">' +
        '<header class="ws-mh"><h4>Late-round pace score</h4><span class="ws-tag untested">Describes fight length, not winners</span></header>' +
        '<div class="ws-line"><span class="ws-scope">Recent, R3+ vs R1</span>' + bfly(m, ln) + '</div>' +
        '<div class="ws-gap">' + (ra && rb ? esc(last(C.a.name) + ': ' + ra.label + ' · ' + last(C.b.name) + ': ' + rb.label) : 'One or both fighters have too little late-round fighting to score.') + '</div>' +
        '<div class="ws-acts">' + ctxBtn('wsx-late') + pinBtn(lateItem) + '</div>' +
        '<div class="ws-ctx" id="wsx-late" hidden><p><b>What it measures.</b> ' + esc(FL.LATE_ROUND_NOTE) + '</p>' +
          evidenceBlock(null, null, custom) +
          '<p class="ws-fine"><b>Sample.</b> ' + esc(samp(C.a, ra)) + '<br>' + esc(samp(C.b, rb)) + '<br>' + esc(FL.SOLID_SAMPLE_NOTE) + '</p></div>' +
      '</article>' +
      '<article class="ws-m">' +
        '<header class="ws-mh"><h4>' + esc(lenM.label) + '</h4><span class="ws-tag untested">Not tested as a predictor</span></header>' +
        '<div class="ws-line"><span class="ws-scope">Last ' + W.RECENT_N + '</span>' + bfly(lenM, lenLn) + '</div>' +
        '<div class="ws-gap">Went the distance: ' + esc(last(C.a.name) + ' ' + decItem.a + ' · ' + last(C.b.name) + ' ' + decItem.b) + '</div>' +
        '<div class="ws-acts">' + ctxBtn('wsx-len') + pinBtn(lenItem) + pinBtn(decItem) + '</div>' +
        '<div class="ws-ctx" id="wsx-len" hidden><p><b>What it measures.</b> Minutes actually fought per fight across the recent window, ' +
          'from the round each fight ended in and the clock it ended on. Short fights can mean finishing opponents or being finished — check the results in Recent form.</p>' +
          evidenceBlock(null) + '</div>' +
      '</article>';
  }

  // ---- recent form -------------------------------------------------------
  function formTab() {
    const chips = (p, list) => list && list.length
      ? '<div class="chips">' + list.map(r => '<span class="chip ' + esc(r.result) + '" title="' +
          esc(r.result + ' vs ' + r.opponentName + ' · ' + r.method) + '">' + esc(r.result) + '</span>').join('') + '</div>'
      : '<div class="ws-fine">' + (C.formOk ? 'No completed UFC fights.' : 'History could not be loaded.') + '</div>';
    const fa = C.factsA, fb = C.factsB;
    const rec = f => f ? f.ufcWins + '-' + f.ufcLosses + (f.ufcFights - f.ufcWins - f.ufcLosses ? ' (' + (f.ufcFights - f.ufcWins - f.ufcLosses) + ' D/NC)' : '') : null;
    const recM = { key: 'ufcwin', label: 'UFC win rate', unit: '%', dp: 0, max: 100 };
    const recLn = W.line(recM, fa ? fa.winPct : null, fb ? fb.winPct : null);
    recLn.aText = fa && fa.ufcFights ? rec(fa) + ' · ' + recLn.aText : null;
    recLn.bText = fb && fb.ufcFights ? rec(fb) + ' · ' + recLn.bText : null;
    const finM = { key: 'finish', label: 'UFC wins by finish', unit: '%', dp: 0, max: 100 };
    const finLn = W.line(finM, fa ? fa.finishPct : null, fb ? fb.finishPct : null);
    finLn.aText = fa && fa.ufcWins ? fa.finishWins + ' of ' + fa.ufcWins + ' · ' + finLn.aText : null;
    finLn.bText = fb && fb.ufcWins ? fb.finishWins + ' of ' + fb.ufcWins + ' · ' + finLn.bText : null;
    const evRec = W.evidence(C.factorRates, 'ufc_record');
    const evFin = W.evidence(C.factorRates, 'finish_rate');
    const streak = f => f && f.streak ? (f.streak.kind === 'W' ? 'Won ' : 'Lost ') + f.streak.count + ' in a row' : '—';
    const layoff = f => f && f.daysSinceLast != null ? Math.round(f.daysSinceLast / 30.4) + ' months (' + f.daysSinceLast + ' days)' : '—';

    const recItem = { id: 'm:ufcrec', cat: 'form', label: 'UFC record (UFC fights only)',
      a: recLn.aText, b: recLn.bText, source: 'Completed UFC fights in CFL data',
      evidence: evRec ? evRec.verdictWords + ' (Factor Lab, ' + evRec.n + ' even-odds fights)' : 'Not tested' };
    const finItem = { id: 'm:finish', cat: 'form', label: 'UFC wins by KO/TKO or submission',
      a: finLn.aText, b: finLn.bText, source: 'Completed UFC fights in CFL data',
      evidence: evFin ? evFin.verdictWords + ' (Factor Lab, ' + evFin.n + ' even-odds fights)' : 'Not tested' };
    const actItem = { id: 'm:activity', cat: 'form', label: 'Streak and time since last fight',
      a: streak(fa) + '; last fought ' + layoff(fa) + ' ago', b: streak(fb) + '; last fought ' + layoff(fb) + ' ago',
      source: 'Completed UFC fights in CFL data' };

    return '<article class="ws-m">' +
        '<header class="ws-mh"><h4>Last ' + W.RECENT_N + ' results, newest first</h4></header>' +
        '<div class="ws-form2"><div><div class="ws-k">' + esc(C.a.name) + '</div>' + chips(C.a, C.formA) + '</div>' +
          '<div><div class="ws-k">' + esc(C.b.name) + '</div>' + chips(C.b, C.formB) + '</div></div>' +
        '<div class="ws-fine">Opponents differ in quality and none of this adjusts for it. The full list, with methods and opponents, is in <a href="#secForm">Last five fights</a>.</div>' +
      '</article>' +
      '<article class="ws-m">' +
        '<header class="ws-mh"><h4>UFC record</h4>' + tested(evRec) + '</header>' +
        '<div class="ws-line"><span class="ws-scope">All UFC fights</span>' + bfly(recM, recLn) + '</div>' +
        '<div class="ws-gap">This is the UFC-only record, not the professional record across every promotion.</div>' +
        '<div class="ws-acts">' + ctxBtn('wsx-rec') + pinBtn(recItem) + '</div>' +
        '<div class="ws-ctx" id="wsx-rec" hidden><p><b>What it measures.</b> Wins as a share of completed UFC fights, counted from the same fight list the page shows. ' +
          'Draws and no contests count as fights but not wins. The professional record in the tale of the tape includes other promotions and is a different number.</p>' +
          evidenceBlock(evRec, 'ufc_record') + '</div>' +
      '</article>' +
      '<article class="ws-m">' +
        '<header class="ws-mh"><h4>Wins by finish</h4>' + tested(evFin) + '</header>' +
        '<div class="ws-line"><span class="ws-scope">All UFC wins</span>' + bfly(finM, finLn) + '</div>' +
        '<div class="ws-acts">' + ctxBtn('wsx-fin') + pinBtn(finItem) + '</div>' +
        '<div class="ws-ctx" id="wsx-fin" hidden><p><b>What it measures.</b> The share of a fighter’s UFC wins that came by KO/TKO or submission rather than on the scorecards. ' +
          'A fighter with two UFC wins can read 0% or 100%; the count beside the percentage is the sample.</p>' + evidenceBlock(evFin, 'finish_rate') + '</div>' +
      '</article>' +
      '<article class="ws-m">' +
        '<header class="ws-mh"><h4>Momentum and activity</h4><span class="ws-tag untested">Not tested as a predictor</span></header>' +
        '<dl class="ws-dl"><dt>Current UFC streak</dt><dd>' + esc(streak(fa)) + '</dd><dd>' + esc(streak(fb)) + '</dd>' +
          '<dt>Time since last UFC fight</dt><dd>' + esc(layoff(fa)) + '</dd><dd>' + esc(layoff(fb)) + '</dd></dl>' +
        '<div class="ws-acts">' + pinBtn(actItem) + '</div>' +
      '</article>';
  }

  // ---- market ------------------------------------------------------------
  function marketTab() {
    const rA = C.rA, rB = C.rB;
    if (!rA || !rB) {
      return '<div class="empty">No sportsbook price captured for this fight yet, so there is nothing to compare. ' +
        'Nothing is estimated in the meantime.</div>';
    }
    const pm = { key: 'cons', label: 'Market consensus', unit: '%', dp: 0, max: 100 };
    const ln = W.line(pm, rA.prob * 100, rB.prob * 100);
    const when = rA.fresh ? rA.fresh.when : M.fmtStampUtc(rA.lastUpdated);
    const books = rA.bookCount != null ? rA.bookCount + ' book' + (rA.bookCount === 1 ? '' : 's') : 'books unknown';
    const mv = M.moveWords(rA.moveSinceBaseline, last(C.a.name));
    const pinDate = new Date().toISOString().slice(0, 10);
    const consItem = { id: 'mk:cons', cat: 'market', label: 'Market consensus (vig removed)',
      a: ln.aText, b: ln.bText, source: 'Sportsbook median, ' + books + ', captured ' + when, sample: 'added ' + pinDate };
    const pxItem = { id: 'mk:px', cat: 'market', label: 'Best price and fair price',
      a: 'best ' + M.fmtAmerican(rA.bestAmerican) + (rA.bestBook ? ' (' + rA.bestBook + ')' : '') + ', fair ' + M.fmtAmerican(rA.fairAmerican),
      b: 'best ' + M.fmtAmerican(rB.bestAmerican) + (rB.bestBook ? ' (' + rB.bestBook + ')' : '') + ', fair ' + M.fmtAmerican(rB.fairAmerican),
      source: 'Captured ' + when + '; fair price is not bettable', sample: 'added ' + pinDate };
    const mvItem = { id: 'mk:move', cat: 'market', label: 'Market movement since first broad capture',
      text: mv.text + (rA.matchedBooks ? ' (' + rA.matchedBooks + ' matched books)' : ''),
      source: 'CFL captures; CFL has never seen a sportsbook opener', sample: 'added ' + pinDate };
    return '<article class="ws-m">' +
        '<header class="ws-mh"><h4>Market consensus</h4><span class="ws-tag mkt">The market’s view, not CFL’s</span></header>' +
        '<div class="ws-split" role="img" aria-label="' + esc(last(C.a.name) + ' ' + ln.aText + ', ' + last(C.b.name) + ' ' + ln.bText) + '">' +
          '<i class="a" style="width:' + (rA.prob * 100).toFixed(1) + '%"><span>' + esc(ln.aText) + '</span></i>' +
          '<i class="b" style="width:' + (rB.prob * 100).toFixed(1) + '%"><span>' + esc(ln.bText) + '</span></i></div>' +
        '<div class="ws-gap">Median sportsbook price with each book’s margin removed · ' + esc(books) + ' · captured ' + esc(when) +
          (rA.fresh && rA.fresh.stale ? ' — stale, check the book' : '') + '</div>' +
        '<div class="ws-acts">' + ctxBtn('wsx-cons') + pinBtn(consItem) + '</div>' +
        '<div class="ws-ctx" id="wsx-cons" hidden><p><b>What it measures.</b> What the sportsbooks, taken together, are implying about this fight once their cut is taken out. ' +
          'It is the market’s number, not a forecast of CFL’s, and CFL publishes no number of its own to set against it.</p>' +
          '<p class="ws-ev"><b>Does it predict winners?</b> Favourites win more often than underdogs, which is what the price says already. ' +
          'Whether a price is worth taking is a different question that this page does not answer.</p>' +
          '<p class="ws-fine">Prices are captured on a schedule, not live. ' + esc(M.baselineCaveat(rA)) + '</p></div>' +
      '</article>' +
      '<article class="ws-m">' +
        '<header class="ws-mh"><h4>Prices and movement</h4></header>' +
        '<dl class="ws-dl"><dt>Best price</dt><dd>' + esc(pxItem.a.replace(/^best |, fair.*/g, '')) + '</dd><dd>' + esc(pxItem.b.replace(/^best |, fair.*/g, '')) + '</dd>' +
          '<dt>Fair price (no vig, not bettable)</dt><dd>' + esc(M.fmtAmerican(rA.fairAmerican)) + '</dd><dd>' + esc(M.fmtAmerican(rB.fairAmerican)) + '</dd></dl>' +
        '<div class="ws-gap">Since the first broad capture: ' + esc(mv.text) + ' · last 24 hours: ' +
          esc(M.moveWords(rA.move24h, last(C.a.name)).text) + ' · books ' + esc(M.spreadWords(rA.spreadPts, rA.bookCount).text) + '</div>' +
        '<div class="ws-acts">' + pinBtn(pxItem) + pinBtn(mvItem) + '</div>' +
        '<div class="ws-fine">The full board, the movement chart and every sportsbook are further down in <a href="#secMarket">the market</a>.</div>' +
      '</article>';
  }


  // ---- key points -------------------------------------------------------
  function keyTab() {
    const pts = C.keyPoints || [];
    if (!pts.length) return '<div class="empty">Not enough data on these two fighters to say anything with confidence.</div>';
    const group = kind => {
      const list = pts.filter(p => p.kind === kind);
      if (!list.length) return '';
      return '<article class="ws-m ws-kp ' + kind + '"><header class="ws-mh"><h4>' + esc(W.KIND_LABEL[kind]) + '</h4>' +
        '<span class="ws-tag k-' + kind + '">' + esc({ fact: 'From the record', calc: 'CFL’s numbers', read: 'Questions, not answers' }[kind]) + '</span></header>' +
        '<ul class="ws-kpl">' + list.map((p, i) => '<li><span>' + esc(p.text) + '</span>' +
          pinBtn({ id: 'kp:' + kind + ':' + p.text.slice(0, 60), cat: 'key', label: W.KIND_LABEL[kind], text: p.text,
                   source: kind === 'fact' ? 'CFL fight records' : kind === 'calc' ? 'Calculated by CFL from the fight records' : 'CFL interpretation — a question, not a forecast' }) +
          '</li>').join('') + '</ul>' +
        (kind === 'read' ? '<div class="ws-fine">Each of these is a question the numbers raise. None of them says who wins, and none of them is a reason to bet.</div>' : '') +
        (kind === 'calc' ? '<div class="ws-fine">' + esc(C.divNote || '') + '</div>' : '') +
      '</article>';
    };
    return group('fact') + group('calc') + group('read');
  }

  // ---- where strikes land ------------------------------------------------
  function mixCard() {
    const mixA = W.strikeMix(C.careerA && C.careerA.totals), mixB = W.strikeMix(C.careerB && C.careerB.totals);
    const bar = (mix, which, labels) => {
      const d = mix && mix[which];
      if (!d) return '<div class="ws-fine">No data.</div>';
      const keys = Object.keys(labels);
      return '<div class="ws-stack" role="img" aria-label="' + esc(keys.map(k => labels[k] + ' ' + Math.round(d[k]) + '%').join(', ')) + '">' +
        keys.map((k, i) => '<i class="s' + i + '" style="width:' + d[k].toFixed(1) + '%">' + (d[k] >= 12 ? esc(Math.round(d[k]) + '%') : '') + '</i>').join('') + '</div>';
    };
    const T = { head: 'Head', body: 'Body', leg: 'Legs' }, P = { distance: 'At distance', clinch: 'In the clinch', ground: 'On the ground' };
    const legend = L => '<div class="ws-slegend">' + Object.keys(L).map((k, i) => '<span><b class="s' + i + '"></b>' + esc(L[k]) + '</span>').join('') + '</div>';
    const txt = (mix, which, L) => mix && mix[which] ? Object.keys(L).map(k => L[k].toLowerCase() + ' ' + Math.round(mix[which][k]) + '%').join(', ') : 'no data';
    const item = { id: 'm:mix', cat: 'striking', label: 'Where significant strikes land (all UFC fights)',
      a: txt(mixA, 'target', T) + '; ' + txt(mixA, 'position', P), b: txt(mixB, 'target', T) + '; ' + txt(mixB, 'position', P),
      source: 'CFL, from the fight records' };
    const col = (p, mix) => '<div><div class="ws-k">' + esc(p.name) + (mix ? ' · ' + mix.landed + ' landed' : '') + '</div>' +
      bar(mix, 'target', T) + bar(mix, 'position', P) + '</div>';
    return '<article class="ws-m"><header class="ws-mh"><h4>Where their strikes land</h4><span class="ws-tag untested">Not tested as a predictor</span></header>' +
      '<div class="ws-form2">' + col(C.a, mixA) + col(C.b, mixB) + '</div>' + legend(T) + legend(P) +
      '<div class="ws-gap">Shares of the significant strikes each fighter landed across all UFC fights. A style description, not a measure of how good it is.</div>' +
      '<div class="ws-acts">' + pinBtn(item) + '</div></article>';
  }

  // ---- submissions -------------------------------------------------------
  function subCard() {
    const ma = C.methodsA, mb = C.methodsB;
    const item = { id: 'm:subs', cat: 'grappling', label: 'Submissions in the UFC',
      a: ma ? ma.win.sub + ' wins by submission, ' + ma.loss.sub + ' losses' : 'no data',
      b: mb ? mb.win.sub + ' wins by submission, ' + mb.loss.sub + ' losses' : 'no data', source: 'Completed UFC fights' };
    return '<article class="ws-m"><header class="ws-mh"><h4>Submission record</h4></header>' +
      '<dl class="ws-dl"><dt>Wins by submission</dt><dd>' + (ma ? ma.win.sub : '—') + '</dd><dd>' + (mb ? mb.win.sub : '—') + '</dd>' +
      '<dt>Losses by submission</dt><dd>' + (ma ? ma.loss.sub : '—') + '</dd><dd>' + (mb ? mb.loss.sub : '—') + '</dd></dl>' +
      '<div class="ws-gap">UFC fights only. Attempts per 15 minutes are in the card above.</div>' +
      '<div class="ws-acts">' + pinBtn(item) + '</div></article>';
  }

  // ---- weight ------------------------------------------------------------
  function weightCard() {
    const lim = W.weightLimit(C.fight.weight_class);
    return '<article class="ws-m"><header class="ws-mh"><h4>Weight</h4></header>' +
      '<dl class="ws-dl"><dt>Division</dt><dd>' + esc(C.fight.weight_class || '—') + '</dd><dd></dd>' +
      '<dt>Division limit</dt><dd>' + (lim ? lim + ' lb' : '—') + '</dd><dd></dd>' +
      '<dt>Stance</dt><dd>' + esc(C.a.stance || '—') + '</dd><dd>' + esc(C.b.stance || '—') + '</dd></dl>' +
      '<div class="ws-gap">The division limit is the most either fighter may weigh at the weigh-in (one pound over is allowed for non-title fights). ' +
      'CFL does not capture weigh-in results, so a missed weight will not show here — check the official weigh-in.</div></article>';
  }

  // ---- round by round ----------------------------------------------------
  function roundsCard() {
    const ra = C.roundsA || [], rb = C.roundsB || [];
    if (!ra.length && !rb.length) return '<article class="ws-m ws-wide"><header class="ws-mh"><h4>Round by round</h4></header><div class="ws-fine">No round data for either fighter.</div></article>';
    const tab = (p, rs) => '<div class="ws-hcol"><div class="ws-hhd">' + esc(p.name) + '</div>' + (rs.length
      ? '<table class="ws-rtab"><thead><tr><th>Round</th><th class="n">Landed</th><th class="n">Absorbed</th><th class="n">Fights</th></tr></thead><tbody>' +
        rs.map(r => '<tr><th>R' + r.round + '</th><td class="n">' + r.landedPm.toFixed(2) + '</td><td class="n">' + r.absorbedPm.toFixed(2) +
          '</td><td class="n mute">' + r.fights + '</td></tr>').join('') + '</tbody></table>'
      : '<div class="ws-hnone">No round data.</div>') + '</div>';
    const fmt = rs => rs.map(r => 'R' + r.round + ' ' + r.landedPm.toFixed(1) + '/' + r.absorbedPm.toFixed(1)).join(', ');
    const item = { id: 'm:rounds', cat: 'cardio', label: 'Round by round: significant strikes landed/absorbed a minute (all UFC fights)',
      a: fmt(ra) || 'no data', b: fmt(rb) || 'no data', source: 'CFL round data' };
    return '<article class="ws-m ws-wide"><header class="ws-mh"><h4>Round by round</h4><span class="ws-tag untested">Not tested as a predictor</span></header>' +
      '<div class="ws-hgrid">' + tab(C.a, ra) + tab(C.b, rb) + '</div>' +
      '<div class="ws-gap">Significant strikes landed and absorbed a minute in each round, across every UFC fight that reached it. A final round counts only the minutes it lasted. ' +
      'Rounds four and five come from five-round fights only, so they rest on fewer fights — the count is beside each one.</div>' +
      '<div class="ws-acts">' + pinBtn(item) + '</div></article>';
  }

  // ---- how they win and lose ---------------------------------------------
  function methodsCard() {
    const row = (p, m) => {
      if (!m) return '<div class="ws-fine">' + esc(p.name) + ': no data.</div>';
      const seg = (side, cls) => {
        const t = m[side].total;
        if (!t) return '<div class="ws-mrow"><span class="ws-k">' + (side === 'win' ? 'Wins' : 'Losses') + '</span><span class="ws-fine">none in the UFC</span></div>';
        return '<div class="ws-mrow"><span class="ws-k">' + (side === 'win' ? 'Wins' : 'Losses') + ' · ' + t + '</span><div class="ws-stack ' + cls + '">' +
          ['ko', 'sub', 'dec', 'other'].filter(k => m[side][k]).map(k =>
            '<i class="m-' + k + '" style="width:' + (m[side][k] / t * 100).toFixed(1) + '%">' + esc({ ko: 'KO', sub: 'SUB', dec: 'DEC', other: 'OTH' }[k] + ' ' + m[side][k]) + '</i>').join('') +
          '</div></div>';
      };
      return '<div><div class="ws-k">' + esc(p.name) + '</div>' + seg('win') + seg('loss') + '</div>';
    };
    const w = m => m ? 'W ' + m.win.ko + ' KO / ' + m.win.sub + ' SUB / ' + m.win.dec + ' DEC; L ' + m.loss.ko + ' KO / ' + m.loss.sub + ' SUB / ' + m.loss.dec + ' DEC' : 'no data';
    const item = { id: 'm:methods', cat: 'form', label: 'How they win and lose (UFC)', a: w(C.methodsA), b: w(C.methodsB), source: 'Completed UFC fights' };
    return '<article class="ws-m"><header class="ws-mh"><h4>How they win and lose</h4></header>' +
      '<div class="ws-form2">' + row(C.a, C.methodsA) + row(C.b, C.methodsB) + '</div>' +
      '<div class="ws-gap">Every completed UFC fight, by how it ended. KO includes TKO and doctor stoppages.</div>' +
      '<div class="ws-acts">' + pinBtn(item) + '</div></article>';
  }

  // ---- quality of opposition ---------------------------------------------
  function oppositionCard() {
    const col = (p, list) => {
      if (!list || !list.length) return '<div class="ws-hcol"><div class="ws-hhd">' + esc(p.name) + '</div><div class="ws-hnone">No completed UFC fights.</div></div>';
      return '<div class="ws-hcol"><div class="ws-hhd">' + esc(p.name) + '</div><table class="ws-htab"><thead><tr><th>Date</th><th>Result</th><th>Opponent</th><th class="n">Their UFC record then</th></tr></thead><tbody>' +
        list.map(r => '<tr><td>' + esc(monthYear(r.date)) + '</td><td>' + esc(r.result + ' · ' + r.method) + '</td><td>' + esc(r.opponentName) + '</td><td class="n">' +
          (r.oppRecord ? (r.oppDebut ? 'UFC debut' : esc(r.oppRecord.w + '-' + r.oppRecord.l + (r.oppRecord.other ? '-' + r.oppRecord.other : ''))) : '—') + '</td></tr>').join('') +
        '</tbody></table></div>';
    };
    const s = list => (list || []).map(r => r.result + ' vs ' + r.opponentName + ' (' + (r.oppRecord ? (r.oppDebut ? 'debut' : r.oppRecord.w + '-' + r.oppRecord.l) : '?') + ')').join('; ');
    const item = { id: 'm:opp', cat: 'form', label: 'Last ' + W.RECENT_N + ' opponents and their UFC record at the time',
      a: s(C.oppA) || 'no data', b: s(C.oppB) || 'no data', source: 'Completed UFC fights' };
    return '<article class="ws-m ws-wide"><header class="ws-mh"><h4>Who they beat, and who beat them</h4><span class="ws-tag untested">Not tested as a predictor</span></header>' +
      '<div class="ws-hgrid">' + col(C.a, C.oppA) + col(C.b, C.oppB) + '</div>' +
      '<div class="ws-gap">Each opponent’s UFC record going into that fight, from our fight records — UFC fights only, so a strong record elsewhere reads as a debut. ' +
      'A record is a rough guide to quality: it does not see who those wins came against.</div>' +
      '<div class="ws-acts">' + pinBtn(item) + '</div></article>';
  }

  // ---- fight context (a section of its own, above the comparison) ----------
  function renderContext() {
    const el = document.getElementById('flContext');
    if (!el) return;
    const facts = [];
    const f = C.fight;
    const lim = W.weightLimit(f.weight_class);
    facts.push(['Bout', (f.is_main_event ? 'Main event · ' : '') + (f.is_title_fight ? 'Title fight · ' : '') + (f.weight_class || 'Weight class not recorded') +
      (lim ? ' (' + lim + ' lb limit)' : '') + (f.scheduled_rounds ? ' · ' + f.scheduled_rounds + ' rounds' : '')]);
    [[C.a, C.factsA], [C.b, C.factsB]].forEach(([p, fx]) => {
      if (!fx) return;
      if (!fx.ufcFights) facts.push([last(p.name), 'UFC debut — no UFC fight data']);
      else facts.push([last(p.name), 'last UFC fight ' + monthYear(fx.lastDate) + ' (' + Math.round(fx.daysSinceLast / 30.4) + ' months ago)' +
        (fx.daysSinceLast >= 365 ? ' — over a year out' : '')]);
    });
    (C.changes || []).forEach(c => facts.push(['Card change', c.fighterName + ' was previously booked here against ' + c.formerOpponent + '; that booking is off the card.']));
    [C.a, C.b].forEach(p => {
      const upd = p.updated_at ? String(p.updated_at).slice(0, 10) : null;
      const cw = p === C.a ? C.careerA : C.careerB;
      const since = upd && cw ? cw.used.filter(u => u.date > upd).length : 0;
      if (since) facts.push(['Data note', last(p.name) + '’s scraped profile was last refreshed ' + monthYear(upd) + ' and misses ' + since +
        ' UFC fight' + (since === 1 ? '' : 's') + '. The page uses CFL’s figures rebuilt from the fight records instead.']);
    });
    el.innerHTML = '<div class="ctx">' +
      '<dl class="ctx-dl">' + facts.map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl>' +
      '<div class="ctx-gap"><b>Not covered yet.</b> CFL has no source for injuries, weigh-in results, short-notice timing or fight-week news, ' +
      'so nothing here reports them. A booking change shows only once the UFCStats card changes. Check the UFC’s official channels for fight-week news.</div>' +
      '</div>';
  }

  // ---- tabs --------------------------------------------------------------
  const TABS = [
    { key: 'key',       label: 'Key points' },
    { key: 'striking',  label: 'Striking' },
    { key: 'grappling', label: 'Grappling' },
    { key: 'cardio',    label: 'Cardio' },
    { key: 'form',      label: 'Recent form' },
    { key: 'physical',  label: 'Physical' },
    { key: 'market',    label: 'Market' },
  ];
  const TAB_NOTE = {
    key:       'What stands out, sorted by how much to trust it: verified facts, numbers CFL calculated, and interpretation. Nothing here says who wins.',
    striking:  '"All UFC fights" is rebuilt by CFL from every completed UFC fight in our data. "Last 5" is the five most recent. Division rank is like for like: each fighter\u2019s own bouts in this weight class over the last three years, against fighters measured the same way.',
    grappling: 'Same sources as Striking: CFL\u2019s figures from the fight records, all UFC fights and the last five.',
    cardio:    'Late-round output and fight length. Neither is a measure of who wins.',
    form:      'Results and record are counted from completed UFC fights only — other promotions are not in our data.',
    physical:  'Fixed facts off the tale of the tape.',
    market:    'Where the sportsbooks have this fight. Prices are captured, not live.',
  };

  function panel(key) {
    if (key === 'key') return keyTab();
    if (key === 'striking') return (W.METRICS.striking || []).map(m => metricCard(key, m)).join('') + mixCard();
    if (key === 'grappling') return (W.METRICS.grappling || []).map(m => metricCard(key, m)).join('') + subCard();
    if (key === 'physical') return (W.METRICS.physical || []).map(m => metricCard(key, m)).join('') + weightCard();
    if (key === 'cardio') return roundsCard() + cardioTab();
    if (key === 'form') return methodsCard() + formTab() + oppositionCard();
    if (key === 'market') return marketTab();
    return (W.METRICS[key] || []).map(m => metricCard(key, m)).join('');
  }

  function renderExplorer() {
    const el = document.getElementById('flExplore');
    if (!el) return;
    el.innerHTML =
      '<div class="ws">' +
        '<div class="ws-tabs" role="tablist" aria-label="Matchup categories">' +
          TABS.map(t => '<button type="button" role="tab" id="wst-' + t.key + '" aria-controls="wsPanel" aria-selected="' +
            (t.key === activeTab) + '" tabindex="' + (t.key === activeTab ? 0 : -1) + '" data-tab="' + t.key + '">' + esc(t.label) + '</button>').join('') +
        '</div>' +
        '<div class="ws-legend"><span class="sw a"></span>' + esc(C.a.name) + '<span class="sw b"></span>' + esc(C.b.name) +
          '<span class="ws-legend-note">Colours only mark whose bar is whose.</span></div>' +
        '<div class="ws-tabnote" id="wsTabNote">' + esc(TAB_NOTE[activeTab]) + '</div>' +
        '<div class="ws-panel" id="wsPanel" role="tabpanel" aria-labelledby="wst-' + activeTab + '">' + panel(activeTab) + '</div>' +
      '</div>';
  }

  function switchTab(key) {
    activeTab = key;
    try { window.sessionStorage.setItem('cfl.ws.tab', key); } catch (e) {}
    renderExplorer();
    const btn = document.getElementById('wst-' + key);
    if (btn) btn.focus();
  }

  // ---- the sheet ---------------------------------------------------------
  function summaryCtx() {
    const ev = C.event;
    return {
      title: C.a.name + ' vs ' + C.b.name,
      subtitle: [C.fight.weight_class, ev && ev.name, ev && window.cfl.formatDate(ev.event_date)].filter(Boolean).join(' · '),
      nameA: last(C.a.name), nameB: last(C.b.name),
      url: location.origin + location.pathname + '?id=' + C.fight.id,
    };
  }

  function renderSheet() {
    const el = document.getElementById('flSheet');
    if (!el) return;
    const items = sheet.items;
    const imp = i => '<select class="sh-imp" data-imp="' + esc(i.id) + '" aria-label="How much this matters to you">' +
      W.IMPORTANCE.map(o => '<option value="' + o.key + '"' + (i.imp === o.key ? ' selected' : '') + '>' + esc(o.label) + '</option>').join('') + '</select>';
    const list = items.length
      ? '<ol class="sh-list">' + items.map((i, k) =>
          '<li class="sh-item">' +
            '<div class="sh-top"><div class="sh-lbl">' + esc(i.label) + '</div>' +
              '<div class="sh-ctl">' + imp(i) +
                '<button type="button" class="sh-ic" data-up="' + esc(i.id) + '" aria-label="Move up"' + (k === 0 ? ' disabled' : '') + '>↑</button>' +
                '<button type="button" class="sh-ic" data-down="' + esc(i.id) + '" aria-label="Move down"' + (k === items.length - 1 ? ' disabled' : '') + '>↓</button>' +
                '<button type="button" class="sh-ic" data-rm="' + esc(i.id) + '" aria-label="Remove">✕</button></div></div>' +
            ((i.a != null || i.b != null)
              ? '<div class="sh-vals"><span><span class="sw a"></span>' + esc(last(C.a.name)) + ' <b>' + esc(i.a == null ? 'no data' : i.a) + '</b></span>' +
                '<span><span class="sw b"></span>' + esc(last(C.b.name)) + ' <b>' + esc(i.b == null ? 'no data' : i.b) + '</b></span></div>' : '') +
            (i.text ? '<div class="sh-text">' + esc(i.text) + '</div>' : '') +
            '<div class="sh-src">' + esc([i.source, i.sample, i.evidence ? 'Tested: ' + i.evidence : null].filter(Boolean).join(' · ')) + '</div>' +
            '<textarea class="sh-note" data-note="' + esc(i.id) + '" rows="2" placeholder="Why this matters to you (optional)">' + esc(i.note || '') + '</textarea>' +
          '</li>').join('') + '</ol>'
      : '<div class="sh-empty"><b>Your sheet is empty.</b> Use <span class="sh-k">+ Add to my sheet</span> on anything in the explorer or under ' +
        '"What stands out", or write your own observation below. You decide what matters and how much — CFL does not rank, score or weigh anything you add.</div>';

    el.innerHTML =
      '<div class="sh">' + list +
        '<div class="sh-add"><label for="shObs">Add your own observation</label>' +
          '<div class="sh-addrow"><input id="shObs" type="text" maxlength="280" placeholder="e.g. Malott has not fought a southpaw in the UFC">' +
          '<button type="button" class="btn" id="shObsAdd">Add</button></div></div>' +
        '<div class="sh-add"><label for="shNotes">My notes</label>' +
          '<textarea id="shNotes" rows="4" placeholder="Anything else you want to remember about this fight.">' + esc(sheet.notes) + '</textarea></div>' +
        '<div class="sh-actions">' +
          '<button type="button" class="btn" id="shCopy">Copy summary</button>' +
          '<button type="button" class="btn ghost" id="shDl">Download .txt</button>' +
          '<button type="button" class="btn ghost" id="shPrint">Print</button>' +
          '<button type="button" class="btn ghost sh-clear" id="shClear"' + (items.length || sheet.notes ? '' : ' disabled') + '>Clear sheet</button>' +
          '<span class="sh-status" id="shStatus" role="status"></span></div>' +
        '<details class="sh-prev"><summary>Preview the summary</summary><pre id="shPre"></pre></details>' +
        '<pre class="sh-print" id="shPrintPre" aria-hidden="true"></pre>' +
        '<div class="foot-note">Saved only in this browser, on this device — no account, nothing sent to CFL. ' +
          'Values are copied when you add them, with the date, so a price you added earlier stays what it was then.' +
          (storageOk ? '' : ' <b>This browser is not letting us save, so the sheet will be lost when you leave.</b>') + '</div>' +
      '</div>';
    refreshSummary();
    updateCount();
  }

  function refreshSummary() {
    const txt = W.summaryText(sheet, summaryCtx());
    const pre = document.getElementById('shPre'); if (pre) pre.textContent = txt;
    const pp = document.getElementById('shPrintPre'); if (pp) pp.textContent = txt;
    return txt;
  }

  function updateCount() {
    const n = sheet.items.length;
    const fab = document.getElementById('wsFab');
    if (fab) {
      fab.hidden = n === 0;
      fab.innerHTML = 'My research sheet <b>' + n + '</b>';
    }
    const j = document.getElementById('jumpSheet');
    if (j) j.textContent = 'My sheet' + (n ? ' (' + n + ')' : '');
  }

  function status(msg) {
    const s = document.getElementById('shStatus');
    if (s) { s.textContent = msg; setTimeout(() => { if (s.textContent === msg) s.textContent = ''; }, 3000); }
  }

  function syncPins() {
    document.querySelectorAll('.ws-pin[data-pin]').forEach(b => {
      const on = W.hasItem(sheet, b.getAttribute('data-pin'));
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
      b.textContent = on ? '✓ On my sheet' : '+ Add to my sheet';
    });
  }

  function commit(rerender) {
    sheet.updatedAt = nowIso();
    saveSheet();
    if (rerender) renderSheet(); else { refreshSummary(); updateCount(); }
    syncPins();
  }

  // ---- events (delegated, bound once) ------------------------------------
  function bind() {
    document.addEventListener('click', ev => {
      const t = ev.target.closest('button, a');
      if (!t) return;
      if (t.dataset.tab) { switchTab(t.dataset.tab); return; }
      if (t.classList.contains('ws-more')) {
        const box = document.getElementById(t.getAttribute('aria-controls'));
        if (!box) return;
        box.hidden = !box.hidden;
        t.setAttribute('aria-expanded', String(!box.hidden));
        t.textContent = box.hidden ? 'What this means' : 'Hide context';
        return;
      }
      if (t.dataset.pin) {
        const id = t.dataset.pin;
        if (W.hasItem(sheet, id)) { W.removeItem(sheet, id, nowIso()); commit(true); }
        else if (registry[id]) { W.addItem(sheet, Object.assign({}, registry[id]), nowIso()); commit(true); status('Added to your sheet'); }
        return;
      }
      if (t.dataset.rm) { W.removeItem(sheet, t.dataset.rm, nowIso()); commit(true); return; }
      if (t.dataset.up) { W.moveItem(sheet, t.dataset.up, -1); commit(true); return; }
      if (t.dataset.down) { W.moveItem(sheet, t.dataset.down, 1); commit(true); return; }
      switch (t.id) {
        case 'shObsAdd': {
          const inp = document.getElementById('shObs');
          const v = (inp.value || '').trim();
          if (!v) { inp.focus(); return; }
          W.addItem(sheet, { id: 'obs:' + Date.now(), cat: 'mine', label: 'My observation', text: v, imp: 'note' }, nowIso());
          commit(true);
          const again = document.getElementById('shObs'); if (again) again.focus();
          return;
        }
        case 'shCopy': {
          const txt = refreshSummary();
          const done = () => status('Summary copied');
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(txt).then(done, () => { fallbackCopy(txt); done(); });
          } else { fallbackCopy(txt); done(); }
          return;
        }
        case 'shDl': {
          const txt = refreshSummary();
          const blob = new Blob([txt], { type: 'text/plain;charset=utf-8' });
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = ('cfl-research-' + last(C.a.name) + '-vs-' + last(C.b.name)).toLowerCase().replace(/[^a-z0-9-]+/g, '-') + '.txt';
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(a.href), 1000);
          return;
        }
        case 'shPrint':
          refreshSummary();
          document.body.classList.add('ws-printing');
          window.print();
          setTimeout(() => document.body.classList.remove('ws-printing'), 500);
          return;
        case 'shClear':
          if (!window.confirm('Clear everything on your research sheet for this fight?')) return;
          sheet = W.emptySheet(C.fight.id);
          commit(true);
          return;
      }
    });
    document.addEventListener('keydown', ev => {
      const t = ev.target;
      if (t && t.getAttribute && t.getAttribute('role') === 'tab' && (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft')) {
        const i = TABS.findIndex(x => x.key === t.dataset.tab);
        const j = (i + (ev.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length;
        ev.preventDefault();
        switchTab(TABS[j].key);
      }
      if (t && t.id === 'shObs' && ev.key === 'Enter') { ev.preventDefault(); document.getElementById('shObsAdd').click(); }
    });
    document.addEventListener('change', ev => {
      const t = ev.target;
      if (t.dataset && t.dataset.imp) {
        const it = sheet.items.find(i => i.id === t.dataset.imp);
        if (it) { it.imp = t.value; commit(false); }
      }
    });
    document.addEventListener('input', ev => {
      const t = ev.target;
      if (t.dataset && t.dataset.note) {
        const it = sheet.items.find(i => i.id === t.dataset.note);
        if (it) { it.note = t.value.slice(0, 1000); commit(false); }
      } else if (t.id === 'shNotes') { sheet.notes = t.value.slice(0, 5000); commit(false); }
    });
    window.addEventListener('afterprint', () => document.body.classList.remove('ws-printing'));
  }

  function fallbackCopy(txt) {
    const ta = document.createElement('textarea');
    ta.value = txt; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    ta.remove();
  }

  // The floating button is a way TO the sheet; once the sheet is on screen it
  // would only cover it.
  function watchSheetInView() {
    const sec = document.getElementById('secSheet');
    if (!sec || !('IntersectionObserver' in window)) return;
    new IntersectionObserver(es => {
      document.body.classList.toggle('ws-sheet-visible', es.some(e => e.isIntersecting));
    }, { rootMargin: '0px 0px -30% 0px' }).observe(sec);
  }

  // ---- public ------------------------------------------------------------
  let bound = false;
  function mount(ctx) {
    C = ctx;
    sheet = loadSheet(ctx.fight.id);
    try {
      const t = window.sessionStorage.getItem('cfl.ws.tab');
      if (t && TABS.some(x => x.key === t)) activeTab = t;
    } catch (e) {}
    if (!bound) { bind(); watchSheetInView(); bound = true; }
    renderExplorer();
    renderContext();
    renderSheet();
  }

  // For other parts of the page ("What stands out") to offer a pin. Returns ''
  // until mount() has run, so nothing can pin into a sheet that is not loaded.
  function pinButton(item) { return sheet ? pinBtn(item) : ''; }

  window.cflWorkspaceUI = { mount, pinButton, syncPins };
})();
