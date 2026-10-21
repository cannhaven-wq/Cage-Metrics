/* ==========================================================================
   Cannon Fight Lab — fight-overview.js
   The pure rules behind Fight Lab's "Matchup overview": the one-screen read of
   both corners that sits above the detailed analytics. No network, no DOM, no
   clock of its own, so the browser and tests/fight-overview.test.js read the
   same rules. The page renders it (fight.html::renderOverview).

   It builds on what already exists and recomputes nothing a second way:
   career rates come from fight-workspace.js::careerWindow (rebuilt from every
   completed UFC fight in `fights`), the fighting style from
   fight-lab.js::disciplineRead (the UFC-listed discipline, copied, never
   calculated — D-030), the late-round score from fight-lab.js::lateRoundRead
   (v_fighter_consistency), the market from market.js::readSide.

   Three rules this file holds:

   1. A TENDENCY IS A MEASUREMENT, NEVER A BACKGROUND. CFL does not know where
      anybody trained. No line here says boxer, kickboxer, wrestler, BJJ,
      Muay Thai or submission specialist; each says what the fight records
      show, with the number and the sample beside it. tests/fight-overview.test.js
      fails if a background label appears in this file's output.

      Nor does any line here name a STYLE. T-082 proposed calculated sub-labels
      (boxing-led, kick-heavy, clinch-heavy, offensive / defensive wrestling,
      submission threat) and was retired 2026-10-21 under D-030: the style a
      page shows is the UFC's listed discipline, and a calculated label beside
      it would compete with it. The measurements those labels would have been
      built from are already here as numbered lines (distance / clinch / ground,
      legs / body / head, takedown attempts, takedown defence, submission
      attempts). See research/backlog/T076_T081_T082_DISPOSITION_2026-10-21.md.

   2. NO TENDENCY FROM A THIN SAMPLE. Under MIN_FIGHTS UFC fights with totals,
      or MIN_MINUTES minutes of fighting, there are no tendency lines at all —
      the overview says how much fighting there is instead. Every threshold
      below is a plain cut-off on the fighter's own numbers; none compares them
      with a league average CFL has not measured.

   3. NOTHING HERE PICKS A SIDE. Two corners are described independently. No
      function adds anything up or returns who "leads" overall.
   ========================================================================== */
(function () {
  'use strict';

  const MIN_FIGHTS = 3;
  const MIN_MINUTES = 25;

  // Labels the overview must never print about a fighter. The UFC-listed
  // discipline (D-030) is shown by the page as a sourced fact, never by this
  // file; the old calculated striker / grappler / mixes-both read is no longer
  // rendered anywhere.
  const BACKGROUND_WORDS = /\b(boxer|boxing|kickboxer|kickboxing|wrestler|wrestling background|muay thai|jiu[- ]jitsu|bjj|judoka|judo|sambo|karate|taekwondo|submission specialist|black belt)\b/i;

  const r1 = v => Math.round(v * 10) / 10;
  const pct = v => Math.round(v) + '%';
  const plural = (n, w, p) => n + ' ' + (n === 1 ? w : (p || w + 's'));

  function clock(minutes) {
    const s = Math.round(minutes * 60);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  // ---- the numbers the overview compares ---------------------------------
  // Career rates rebuilt from fight records; the scraped profile figure only
  // when there are no fight records with totals, and the source says which.
  function statLine(fighter, career) {
    const c = career && career.rates && career.fights ? career.rates : null;
    if (c) {
      return {
        source: 'fights', fights: career.fights, minutes: career.minutes,
        slpm: c.slpm, str_acc: c.str_acc, sapm: c.sapm, str_def: c.str_def,
        td_avg: c.td_avg, td_acc: c.td_acc, td_def: c.td_def, sub_avg: c.sub_avg,
        ctrl15: c.ctrl15, kd: career.totals ? career.totals.kd : null,
        tdA: career.totals ? career.totals.tdA : null, oppTdA: career.totals ? career.totals.oppTdA : null,
        oppTdL: career.totals ? career.totals.oppTdL : null,
      };
    }
    const n = v => (v == null || v === '' || !Number.isFinite(+v)) ? null : +v;
    const any = ['slpm', 'str_acc', 'sapm', 'str_def', 'td_avg', 'td_acc', 'td_def', 'sub_avg']
      .some(k => n(fighter && fighter[k]) != null && n(fighter[k]) !== 0);
    if (!any) return { source: 'none' };
    return {
      source: 'profile', fights: null, minutes: null,
      slpm: n(fighter.slpm), str_acc: n(fighter.str_acc), sapm: n(fighter.sapm), str_def: n(fighter.str_def),
      td_avg: n(fighter.td_avg), td_acc: n(fighter.td_acc), td_def: n(fighter.td_def), sub_avg: n(fighter.sub_avg),
      ctrl15: null, kd: null, tdA: null, oppTdA: null, oppTdL: null,
    };
  }

  // ---- how far fights go -------------------------------------------------
  // From the completed-fight list (fight-lab.js::completedFights, newest first).
  function distance(completed, fighterId) {
    const out = { fights: 0, reachedR3: 0, intoR4: 0, decisions: { w: 0, l: 0, other: 0, total: 0 },
                  finishedIn: { r1: 0, r2: 0, r3plus: 0 } };
    (completed || []).forEach(({ f }) => {
      const r = +f.end_round;
      if (!r) return;
      out.fights += 1;
      if (r >= 3) out.reachedR3 += 1;
      if (r >= 4) out.intoR4 += 1;
      const dec = /^decision/i.test(String(f.method || ''));
      if (dec) {
        out.decisions.total += 1;
        if (f.winner_id == null) out.decisions.other += 1;
        else if (f.winner_id === fighterId) out.decisions.w += 1;
        else out.decisions.l += 1;
      } else if (f.winner_id === fighterId) {
        if (r === 1) out.finishedIn.r1 += 1; else if (r === 2) out.finishedIn.r2 += 1; else out.finishedIn.r3plus += 1;
      }
    });
    return out;
  }

  // ---- tendencies --------------------------------------------------------
  // x: { stats (statLine), mix (fight-workspace strikeMix), methods
  //      (fight-workspace methods), facts (fight-workspace formFacts) }.
  // Returns { lines, results, reason }. `lines` are statistical tendencies
  // (rates, needing the sample floor); `results` are recorded outcomes — how
  // UFC fights actually ended — which are counts, never a tendency, and are
  // kept apart so a thin sample cannot dress a count up as a pattern. reason
  // is set when there are no tendency lines and says why.
  function tendencies(x) {
    const s = x.stats || {};
    const lines = [];
    const results = [];
    const push = (key, text, basis) => lines.push({ key, text, basis });
    const record = (key, text, basis) => results.push({ key, text, basis });

    if (s.source !== 'fights' || (s.fights || 0) < MIN_FIGHTS || (s.minutes || 0) < MIN_MINUTES) {
      const why = s.source === 'fights'
        ? 'Only ' + plural(s.fights || 0, 'UFC fight') + ' (' + Math.round(s.minutes || 0) + ' minutes) with fight totals on record — too little to describe statistical tendencies.'
        : 'No UFC fight totals on record — statistical tendencies are not described from a profile summary alone.';
      // Finishing methods are recorded results, not rates: they are listed
      // separately and never presented as a tendency.
      methodLines(x, record);
      return { lines, results, reason: why };
    }
    const basis = 'UFC career, ' + plural(s.fights, 'fight') + ', ' + Math.round(s.minutes) + ' min';
    const mix = x.mix;

    // Where and what they land.
    if (mix && mix.position) {
      const p = mix.position;
      if (p.distance >= 70) push('distance', 'Does most of their striking at range: ' + pct(p.distance) + ' of landed significant strikes come at distance.', basis);
      if (p.clinch >= 20) push('clinch', 'Works in the clinch: ' + pct(p.clinch) + ' of landed significant strikes come from the clinch.', basis);
      if (p.ground >= 25) push('ground', 'Does damage on the mat: ' + pct(p.ground) + ' of landed significant strikes come on the ground.', basis);
    }
    if (mix && mix.target) {
      const t = mix.target;
      if (t.leg >= 20) push('legs', 'Attacks the legs: ' + pct(t.leg) + ' of landed significant strikes go to the legs.', basis);
      if (t.body >= 20) push('body', 'Goes to the body: ' + pct(t.body) + ' of landed significant strikes land to the body.', basis);
      if (t.head >= 80) push('head', 'Head-focused: ' + pct(t.head) + ' of landed significant strikes go to the head.', basis);
    }
    // Output against what comes back — a comparison with their own opponents.
    if (s.slpm != null && s.sapm != null) {
      const d = s.slpm - s.sapm;
      if (d >= 1) push('outland', 'Out-lands opponents: ' + r1(s.slpm) + ' significant strikes landed a minute against ' + r1(s.sapm) + ' absorbed.', basis);
      else if (d <= -1) push('outlanded', 'Absorbs more than they land: ' + r1(s.sapm) + ' significant strikes absorbed a minute against ' + r1(s.slpm) + ' landed.', basis);
    }
    if (s.kd != null && s.kd >= 3) push('kd', 'Has scored ' + s.kd + ' knockdowns in UFC fights.', basis);

    // Wrestling and control, by what happened, not by reputation.
    const minutes = s.minutes;
    const tdA15 = s.tdA != null ? s.tdA / minutes * 15 : null;
    if (tdA15 != null && tdA15 >= 3) {
      push('shoots', 'Looks for takedowns: ' + r1(tdA15) + ' attempts per 15 minutes' +
        (s.td_acc != null ? ', landing ' + pct(s.td_acc) : '') + '.', basis);
    } else if (s.tdA === 0 && minutes >= 45) {
      push('noshot', 'Has not attempted a takedown in ' + Math.round(minutes) + ' UFC minutes.', basis);
    }
    if (s.ctrl15 != null && s.ctrl15 >= 3) push('control', 'Holds position: ' + clock(s.ctrl15) + ' of control time per 15 minutes.', basis);
    if (s.sub_avg != null && s.sub_avg >= 1) push('subtries', 'Attempts submissions: ' + r1(s.sub_avg) + ' per 15 minutes.', basis);
    if (s.oppTdA != null && s.oppTdA >= 5 && s.td_def != null) {
      const stopped = s.oppTdA - (s.oppTdL || 0);
      if (s.td_def >= 80) push('tddef', 'Hard to take down: stopped ' + stopped + ' of ' + s.oppTdA + ' takedown attempts.', basis);
      else if (s.td_def <= 50) push('tdweak', 'Has been taken down on ' + (s.oppTdL || 0) + ' of ' + s.oppTdA + ' attempts against them.', basis);
    }

    methodLines(x, record);

    const f = x.facts;
    if (f && f.last5Count >= 4 && f.last5Distance >= 3) {
      record('judges', f.last5Distance + ' of their last ' + f.last5Count + ' fights went to the judges.', 'Last ' + f.last5Count + ' UFC fights');
    }
    return { lines, results, reason: lines.length ? null : 'Nothing in their UFC numbers stands out past the cut-offs CFL uses here.' };
  }

  // How they win and lose — recorded results, so they need no rate sample.
  function methodLines(x, push) {
    const m = x.methods;
    if (!m) return;
    const basis = 'Completed UFC fights';
    const w = m.win, l = m.loss;
    if (w.total >= 3) {
      if (w.ko / w.total >= 0.5) push('kowins', w.ko + ' of ' + w.total + ' UFC wins' + ' came by KO/TKO.', basis);
      if (w.sub / w.total >= 0.4) push('subwins', w.sub + ' of ' + w.total + ' UFC wins' + ' came by submission.', basis);
      if (w.dec / w.total >= 0.6) push('decwins', w.dec + ' of ' + w.total + ' UFC wins' + ' went to a decision.', basis);
    }
    if (l.total >= 2) {
      if (l.ko / l.total >= 0.6) push('kolosses', l.ko + ' of ' + l.total + ' UFC losses' + ' came by KO/TKO.', basis);
      if (l.sub / l.total >= 0.6) push('sublosses', l.sub + ' of ' + l.total + ' UFC losses' + ' came by submission.', basis);
    }
  }

  // Strings safe for a fighter overview: never a training background.
  function hasBackgroundClaim(text) { return BACKGROUND_WORDS.test(String(text || '')); }

  const OVERVIEW_NOTE =
    'Tendencies are measured from UFC fight records, not from reputation or where someone trained — CFL does ' +
    'not hold training backgrounds. Each line shows the number behind it and appears only past a fixed cut-off on ' +
    'the fighter’s own numbers, with at least ' + MIN_FIGHTS + ' UFC fights and ' + MIN_MINUTES + ' minutes on record. ' +
    'Recorded results (how their UFC fights ended) are listed separately: they are a count of what happened, not a tendency. ' +
    'Nothing here is a pick: two fighters are described, not compared into a winner.';

  const api = { MIN_FIGHTS, MIN_MINUTES, BACKGROUND_WORDS, statLine, distance, tendencies, hasBackgroundClaim, clock, OVERVIEW_NOTE };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflOverview = api;
})();
