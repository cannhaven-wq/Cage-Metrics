/* ==========================================================================
   Cannon Fight Lab — shared JS
   Loaded by every page. Provides:
     - window.cflSupabase  → Supabase client
     - window.cfl          → helpers namespace
   ========================================================================== */

(function () {
  // --------- Supabase client ---------
  const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
  const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
  // The default Supabase JS client uses a lock mechanism around auth state
  // that can get stuck in some browsers, causing all subsequent DB queries
  // to hang on a pending Promise. We pass an explicit auth config that uses
  // a no-op lock to avoid the bug. See:
  // https://github.com/supabase/auth-js/issues/762
  window.cflSupabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      storage: window.localStorage,
      storageKey: 'cfl-auth',
      // No-op lock: we don't have multi-tab use cases that need synchronization
      // and the default lock has a hang bug. Replace with a passthrough.
      lock: async (name, acquireTimeout, fn) => fn()
    }
  });

  // --------- Helpers ---------
  const cfl = {};

  // --------- Model registry (July 2026 three-product restructure) ---------
  // The models the public site shows. All six are live. Caveats: v1/v2 don't
  // beat the closing favorite, and v5 was trained with the market line — its
  // accuracy is partly the market's own and it can't produce a pick before a
  // line exists. Each model's tagline states its limit. Story: edges.html.
  //
  // trainEnd is duplicated here (not just in model_versions) on purpose: it
  // is the client-side floor below which a model's graded stats must never be
  // displayed, even if the DB row's test_start_date is wrong. That exact bug
  // is how v6 publicly claimed a 2021-2026 "never seen" record that included
  // four years of its own training data.
  cfl.MODELS = {
    v6: {
      slot: 'roi',
      name: 'Value — beats the opener',
      tagline: 'Hunts fights where the opening line is wrong. Every pick locked at first write, never re-priced.',
      trainEnd: '2024-12-31',
      money: true,
    },
    v3: {
      slot: 'accuracy',
      name: 'Fight IQ — tape only',
      tagline: 'Predicts winners from fighter data alone. Never sees a betting line, so its number is fully independent of the market.',
      trainEnd: '2022-12-31',
      money: false,
    },
    v5: {
      slot: 'accuracy',
      name: 'Accuracy v5 — market + tape',
      tagline: 'XGBoost on 44 features including the Vegas line. Its 70% is tied to the market, so it reads best as a benchmark, not a live pre-line pick.',
      trainEnd: '2023-12-31',
      money: false,
    },
    v4: {
      slot: 'accuracy',
      name: 'Stacker — models on models',
      tagline: 'Blends v1/v2/v3 into one number, plus the opener. Sharper on a smaller, higher-conviction pick set.',
      trainEnd: '2024-12-31',
      money: false,
    },
    v2: {
      slot: 'accuracy',
      name: 'Elo — opponent quality',
      tagline: "Baseline tape stats plus a fighter Elo, so beating a contender counts more than beating a debutant.",
      trainEnd: '2022-12-31',
      money: false,
    },
    v1: {
      slot: 'accuracy',
      name: 'Baseline — tape only',
      tagline: 'The reference model: rolling fighter stats, no opponent-quality signal. Shows what every later feature actually buys.',
      trainEnd: '2022-12-31',
      money: false,
    },
  };
  cfl.PUBLIC_MODELS = ['v6', 'v3', 'v5', 'v4', 'v2', 'v1'];

  cfl.modelName = function (id, dbName) {
    return (cfl.MODELS[id] && cfl.MODELS[id].name) || dbName || id;
  };

  // One plain-English definition per model, reused by every picker and the
  // "How each model works" panel. 'engine' and 'consensus' aren't in
  // cfl.MODELS, so they're handled explicitly. Single source of truth — edit
  // the tagline in cfl.MODELS / cfl.ENGINE and it updates everywhere.
  cfl.modelDef = function (id) {
    if (id === 'engine') return cfl.ENGINE.accuracy.tagline;
    if (id === 'consensus') return 'The average call across every model shown — a fight only counts when the models agree. A useful gut-check, but only as sound as the models feeding it.';
    return (cfl.MODELS[id] && cfl.MODELS[id].tagline) || '';
  };

  // --------- Engine (July 2026 "one engine" rebuild) ---------
  // The engine is one brain with two product faces. It publishes to the
  // model_picks / model_edges tables (read via the graded views below), NOT
  // model_predictions — so it deliberately lives outside cfl.MODELS, whose
  // keys are model_version values queried against model_predictions.
  // engine_v1/engine_v2/… rows are one model family: never filter by
  // model_version (the string is provenance, shown as-is). Simulated-vs-live
  // maps to the source column ('backtest' / 'live'). Every backtest row is
  // out-of-sample by construction (walk-forward; the uncalibrated fold 0 is
  // excluded at publish), so no trainEnd window clamp applies here.
  cfl.ENGINE = {
    family: 'engine',
    accuracy: {
      name: 'Fight IQ — tape only',
      tagline: 'One calibrated winner probability per fight, built from fighter history, fight stats, and physical attributes. Never sees a betting line.',
    },
    roi: {
      name: 'Value — where the price is wrong',
      tagline: 'Flags fights where the model disagrees with the vig-free market price, with a disciplined stake attached. Live picks are locked at first write, never re-priced.',
    },
    tiers: { Lock: 0.65, Pick: 0.57 }, // mirrors cfl_engine/faces.py tier_of
  };

  // Graded-view loaders. Both views join fights server-side: hit/won are NULL
  // while the fight is unresolved (render as pending, never as a loss). Pass a
  // modifier to filter, e.g. cfl.fetchEnginePicks(q => q.eq('source', 'live')).
  cfl.fetchEnginePicks = function (mod) {
    const sb = window.cflSupabase;
    return cfl.fetchAll(() => {
      const q = sb.from('v_model_picks_graded').select('*')
        .order('event_date', { ascending: true }).order('id', { ascending: true });
      return mod ? mod(q) : q;
    });
  };
  cfl.fetchEngineEdges = function (mod) {
    const sb = window.cflSupabase;
    return cfl.fetchAll(() => {
      const q = sb.from('v_model_edges_graded').select('*')
        .order('event_date', { ascending: true }).order('id', { ascending: true });
      return mod ? mod(q) : q;
    });
  };

  // Honest out-of-sample floor for a model's graded stats: the later of the
  // DB's test_start_date and the day after the model's training cutoff.
  cfl.modelWindowStart = function (id, testStartDate) {
    const m = cfl.MODELS[id];
    let floor = testStartDate || null;
    if (m && m.trainEnd) {
      const d = new Date(m.trainEnd + 'T00:00:00Z');
      d.setUTCDate(d.getUTCDate() + 1);
      const afterTrain = d.toISOString().slice(0, 10);
      if (!floor || afterTrain > floor) floor = afterTrain;
    }
    return floor;
  };

  cfl.initials = function (name) {
    if (!name) return '?';
    return name.split(/\s+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  };

  // ---- Country of origin -------------------------------------------------
  // Flags are drawn as CSS gradients rather than images or emoji. Flag emoji
  // have no glyphs on Windows (they render as the bare letters "US", "BR"),
  // and an image set would be ~26 extra requests on a full card. A gradient is
  // one string, scales to any size, and at low opacity reads as the flag's
  // colours — which is all a background tint has to do.
  //
  // Each entry is [orientation, ...colours]: 'v' vertical bands, 'h'
  // horizontal bands, 'd' diagonal (used for flags whose real design is a
  // cross, canton, or emblem that bands cannot approximate).
  const FLAG_COLORS = {
    US: ['h', '#b22234', '#ffffff', '#3c3b6e'],
    BR: ['d', '#009b3a', '#ffdf00', '#002776'],
    MX: ['v', '#006847', '#ffffff', '#ce1126'],
    CA: ['v', '#d80621', '#ffffff', '#d80621'],
    RU: ['h', '#ffffff', '#0039a6', '#d52b1e'],
    GB: ['d', '#012169', '#ffffff', '#c8102e'],
    IE: ['v', '#169b62', '#ffffff', '#ff883e'],
    AU: ['d', '#012169', '#ffffff', '#e4002b'],
    NZ: ['d', '#012169', '#ffffff', '#c8102e'],
    CN: ['d', '#de2910', '#ffde00', '#de2910'],
    JP: ['d', '#ffffff', '#bc002d', '#ffffff'],
    KR: ['d', '#ffffff', '#cd2e3a', '#0047a0'],
    KP: ['h', '#024fa2', '#ffffff', '#ed1c27'],
    FR: ['v', '#002395', '#ffffff', '#ed2939'],
    DE: ['h', '#000000', '#dd0000', '#ffce00'],
    ES: ['h', '#aa151b', '#f1bf00', '#aa151b'],
    IT: ['v', '#008c45', '#f4f5f0', '#cd212a'],
    NL: ['h', '#ae1c28', '#ffffff', '#21468b'],
    BE: ['v', '#000000', '#fdda24', '#ef3340'],
    SE: ['d', '#006aa7', '#fecc00', '#006aa7'],
    NO: ['d', '#ba0c2f', '#ffffff', '#00205b'],
    DK: ['d', '#c60c30', '#ffffff', '#c60c30'],
    FI: ['d', '#ffffff', '#002f6c', '#ffffff'],
    IS: ['d', '#02529c', '#ffffff', '#dc1e35'],
    PL: ['h', '#ffffff', '#dc143c', '#dc143c'],
    CZ: ['d', '#11457e', '#ffffff', '#d7141a'],
    SK: ['h', '#ffffff', '#0b4ea2', '#ee1c25'],
    AT: ['h', '#ed2939', '#ffffff', '#ed2939'],
    CH: ['d', '#d52b1e', '#ffffff', '#d52b1e'],
    PT: ['v', '#046a38', '#046a38', '#da291c'],
    GR: ['h', '#0d5eaf', '#ffffff', '#0d5eaf'],
    HR: ['h', '#ff0000', '#ffffff', '#171796'],
    RS: ['h', '#c6363c', '#0c4076', '#ffffff'],
    BA: ['d', '#002395', '#fecb00', '#002395'],
    SI: ['h', '#ffffff', '#005da4', '#ed1c24'],
    HU: ['h', '#ce2939', '#ffffff', '#477050'],
    RO: ['v', '#002b7f', '#fcd116', '#ce1126'],
    BG: ['h', '#ffffff', '#00966e', '#d62612'],
    UA: ['h', '#0057b7', '#0057b7', '#ffd700'],
    BY: ['h', '#c8313e', '#ffffff', '#4aa657'],
    MD: ['v', '#0046ae', '#ffd200', '#cc092f'],
    LT: ['h', '#fdb913', '#006a44', '#c1272d'],
    LV: ['h', '#9e3039', '#ffffff', '#9e3039'],
    EE: ['h', '#0072ce', '#000000', '#ffffff'],
    GE: ['d', '#ffffff', '#ff0000', '#ffffff'],
    AM: ['h', '#d90012', '#0033a0', '#f2a800'],
    AZ: ['h', '#0092bc', '#ed2939', '#3f9c35'],
    KZ: ['d', '#00afca', '#fec50c', '#00afca'],
    UZ: ['h', '#0099b5', '#ffffff', '#1eb53a'],
    KG: ['d', '#e8112d', '#ffef00', '#e8112d'],
    TJ: ['h', '#cc0000', '#ffffff', '#006600'],
    TM: ['v', '#28ae66', '#ffffff', '#28ae66'],
    TR: ['d', '#e30a17', '#ffffff', '#e30a17'],
    IR: ['h', '#239f40', '#ffffff', '#da0000'],
    IQ: ['h', '#ce1126', '#ffffff', '#000000'],
    IL: ['h', '#ffffff', '#0038b8', '#ffffff'],
    LB: ['h', '#ed1c24', '#ffffff', '#00a651'],
    JO: ['h', '#000000', '#ffffff', '#007a3d'],
    SY: ['h', '#ce1126', '#ffffff', '#000000'],
    SA: ['d', '#006c35', '#ffffff', '#006c35'],
    AE: ['h', '#00732f', '#ffffff', '#000000'],
    BH: ['v', '#ffffff', '#ce1126', '#ce1126'],
    KW: ['h', '#007a3d', '#ffffff', '#ce1126'],
    QA: ['v', '#ffffff', '#8a1538', '#8a1538'],
    OM: ['h', '#ffffff', '#db161b', '#008000'],
    AF: ['v', '#000000', '#d32011', '#007a36'],
    PK: ['v', '#ffffff', '#01411c', '#01411c'],
    IN: ['h', '#ff9933', '#ffffff', '#138808'],
    NP: ['d', '#dc143c', '#ffffff', '#003893'],
    BD: ['d', '#006a4e', '#f42a41', '#006a4e'],
    LK: ['d', '#ffbe29', '#8d153a', '#00534e'],
    TH: ['h', '#a51931', '#f4f5f8', '#2d2a4a'],
    VN: ['d', '#da251d', '#ffff00', '#da251d'],
    PH: ['d', '#0038a8', '#ffffff', '#ce1126'],
    ID: ['h', '#ce1126', '#ce1126', '#ffffff'],
    MY: ['h', '#010066', '#ffffff', '#cc0001'],
    SG: ['h', '#ed2939', '#ffffff', '#ffffff'],
    MM: ['h', '#fecb00', '#34b233', '#ea2839'],
    KH: ['h', '#032ea1', '#e00025', '#032ea1'],
    LA: ['h', '#ce1126', '#002868', '#ce1126'],
    MN: ['v', '#c4272f', '#015197', '#c4272f'],
    AR: ['h', '#74acdf', '#ffffff', '#74acdf'],
    CL: ['d', '#0039a6', '#ffffff', '#d52b1e'],
    PE: ['v', '#d91023', '#ffffff', '#d91023'],
    CO: ['h', '#fcd116', '#003893', '#ce1126'],
    VE: ['h', '#ffcc00', '#00247d', '#cf142b'],
    EC: ['h', '#ffdd00', '#034ea2', '#ed1c24'],
    BO: ['h', '#d52b1e', '#f9e300', '#007a33'],
    UY: ['d', '#0038a8', '#ffffff', '#0038a8'],
    PY: ['h', '#d52b1e', '#ffffff', '#0038a8'],
    PA: ['d', '#005293', '#ffffff', '#d21034'],
    CR: ['h', '#002b7f', '#ffffff', '#ce1126'],
    GT: ['v', '#4997d0', '#ffffff', '#4997d0'],
    HN: ['h', '#0073cf', '#ffffff', '#0073cf'],
    NI: ['h', '#0067c6', '#ffffff', '#0067c6'],
    SV: ['h', '#0f47af', '#ffffff', '#0f47af'],
    CU: ['d', '#002a8f', '#ffffff', '#cf142b'],
    DO: ['d', '#002d62', '#ffffff', '#ce1126'],
    PR: ['d', '#ed0000', '#ffffff', '#0050f0'],
    JM: ['d', '#009b3a', '#fed100', '#000000'],
    TT: ['d', '#da1a35', '#ffffff', '#000000'],
    HT: ['h', '#00209f', '#00209f', '#d21034'],
    BS: ['h', '#00abc9', '#ffc72c', '#000000'],
    SR: ['h', '#377e3f', '#ffffff', '#b40a2d'],
    GY: ['d', '#009e49', '#fcd116', '#ce1126'],
    BZ: ['h', '#003f87', '#ce1126', '#003f87'],
    NG: ['v', '#008751', '#ffffff', '#008751'],
    GH: ['h', '#ce1126', '#fcd116', '#006b3f'],
    CM: ['v', '#007a5e', '#ce1126', '#fcd116'],
    ZA: ['d', '#007749', '#ffb612', '#de3831'],
    KE: ['h', '#000000', '#bb0000', '#006600'],
    MA: ['d', '#c1272d', '#006233', '#c1272d'],
    DZ: ['v', '#006233', '#ffffff', '#d21034'],
    TN: ['d', '#e70013', '#ffffff', '#e70013'],
    EG: ['h', '#ce1126', '#ffffff', '#000000'],
    SN: ['v', '#00853f', '#fdef42', '#e31b23'],
    AO: ['h', '#ce1126', '#000000', '#ce1126'],
    CG: ['d', '#009543', '#fbde4a', '#dc241f'],
    CD: ['d', '#007fff', '#f7d618', '#ce1021'],
    CI: ['v', '#f77f00', '#ffffff', '#009e60'],
    ML: ['v', '#14b53a', '#fcd116', '#ce1126'],
    SD: ['h', '#d21034', '#ffffff', '#000000'],
    ET: ['h', '#009a49', '#fedd00', '#da121a'],
    TZ: ['d', '#1eb53a', '#000000', '#00a3dd'],
    UG: ['h', '#000000', '#fcdc04', '#d90000'],
    ZW: ['h', '#319208', '#ffd200', '#de2010'],
    MZ: ['h', '#007168', '#ffffff', '#d21034'],
    GU: ['d', '#0071bc', '#ffffff', '#0071bc'],
    WS: ['d', '#ce1126', '#002b7f', '#ce1126'],
    AS: ['d', '#002b7f', '#ffffff', '#c8102e'],
    FJ: ['d', '#68bfe5', '#ffffff', '#68bfe5'],
    TO: ['d', '#c10000', '#ffffff', '#c10000'],
    PG: ['d', '#000000', '#ce1126', '#fcd116'],
    CV: ['h', '#003893', '#ffffff', '#cf2027'],
  };

  const FLAG_ANGLE = { v: '90deg', h: '180deg', d: '125deg' };

  // A CSS gradient approximating a country's flag, for use as a background
  // tint. Returns null for unknown or missing codes so callers fall back to a
  // plain surface rather than an arbitrary colour.
  cfl.flagTint = function (code) {
    const spec = FLAG_COLORS[String(code || '').toUpperCase()];
    if (!spec) return null;
    const colors = spec.slice(1);
    const angle = FLAG_ANGLE[spec[0]] || '180deg';
    const step = 100 / colors.length;
    const stops = colors.map((c, i) => c + ' ' + (i * step) + '% ' + ((i + 1) * step) + '%');
    return 'linear-gradient(' + angle + ', ' + stops.join(', ') + ')';
  };

  cfl.hasFlag = function (code) {
    return !!FLAG_COLORS[String(code || '').toUpperCase()];
  };

  // Put an upcoming card's fights into true card order and drop dead bookings.
  //
  // The fights table has two decay modes this compensates for:
  //  - upserts key on ufc_fight_id, so a booking that drops off the UFCStats
  //    event page stops being updated and can keep a stale is_main_event=true
  //    forever (two "main events", the older row id winning the sort);
  //  - opponent changes create a NEW ufc_fight_id, and nothing pruned the old
  //    row, so the same fighter can appear in two fights on one card.
  //
  // Strategy, in order of trust:
  //  1. rows the scraper marked is_active=false are dropped (column may not
  //     exist yet — absent reads as undefined, which passes);
  //  2. a fighter booked in two fights keeps only the newest row (higher id);
  //  3. the real main event is resolved from the event name ("...: X vs. Y"),
  //     which is authoritative in a way the flag isn't; ties on the flag keep
  //     the newest claimant. The winning row's is_main_event is corrected in
  //     place so page labels agree with the sort;
  //  4. sort by bout_order when the scraper has written it, else main event
  //     first then insert id (id order matches page order within one scrape).
  cfl.orderCard = function (fights, eventName) {
    if (!Array.isArray(fights) || fights.length === 0) return fights || [];
    let rows = fights.filter(f => f.is_active !== false);

    const newestByFighter = new Map();
    rows.forEach(f => {
      [f.fighter_a_id, f.fighter_b_id].forEach(id => {
        if (id == null) return;
        const prev = newestByFighter.get(id);
        if (!prev || f.id > prev.id) newestByFighter.set(id, f);
      });
    });
    rows = rows.filter(f =>
      (f.fighter_a_id == null || newestByFighter.get(f.fighter_a_id) === f) &&
      (f.fighter_b_id == null || newestByFighter.get(f.fighter_b_id) === f));

    let mainRow = null;
    const m = (eventName || '').match(/:\s*(.+?)\s+vs\.?\s+(.+)$/i);
    if (m) {
      const n1 = m[1].trim().toLowerCase();
      const n2 = m[2].trim().toLowerCase();
      mainRow = rows.find(f => {
        const names = ((f.fighter_a_name || '') + '|' + (f.fighter_b_name || '')).toLowerCase();
        return names.includes(n1) && names.includes(n2);
      }) || null;
    }
    if (!mainRow) {
      const claims = rows.filter(f => f.is_main_event);
      if (claims.length) mainRow = claims.reduce((a, b) => (b.id > a.id ? b : a));
    }
    rows.forEach(f => { f.is_main_event = (f === mainRow); });

    const hasOrder = rows.some(f => f.bout_order != null);
    rows.sort((a, b) => {
      if (hasOrder && a.bout_order != null && b.bout_order != null) return a.bout_order - b.bout_order;
      if (a.is_main_event !== b.is_main_event) return a.is_main_event ? -1 : 1;
      return a.id - b.id;
    });
    return rows;
  };

  cfl.escapeHtml = function (s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  };

  cfl.formatRecord = function (w, l, d) {
    if (w == null && l == null && d == null) return '—';
    return `${w ?? 0}-${l ?? 0}-${d ?? 0}`;
  };

  cfl.formatHeight = function (inches) {
    if (inches == null) return '—';
    const ft = Math.floor(inches / 12);
    const inch = Math.round(inches % 12);
    return `${ft}'${inch}"`;
  };

  cfl.formatReach = function (inches) {
    if (inches == null) return '—';
    return `${inches}"`;
  };

  cfl.formatDate = function (isoDate) {
    if (!isoDate) return '—';
    const d = new Date(isoDate + 'T00:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  };

  cfl.formatDateShort = function (isoDate) {
    if (!isoDate) return '—';
    const d = new Date(isoDate + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  cfl.daysUntil = function (isoDate) {
    if (!isoDate) return null;
    const target = new Date(isoDate + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((target - today) / (1000 * 60 * 60 * 24));
  };

  // --------- Current-event window ---------
  // How long a card stays on the home page / Card Lab after its own date ends,
  // before we roll over to the next upcoming event. Local time, not UTC.
  // 6h keeps a Saturday-night card up through Sunday sunrise, then rolls.
  cfl.ROLLOVER_HOURS = 6;

  // Returns { fromStr, todayStr } — the inclusive event_date range that counts
  // as "happening now". Single source of truth: index.html and card-lab.html
  // both select the current event with this window.
  cfl.eventWindow = function (nowOverride) {
    const now = nowOverride || new Date();
    const from = new Date(now.getTime() - cfl.ROLLOVER_HOURS * 3600000);
    return { fromStr: localDateStr(from), todayStr: localDateStr(now) };
  };

  function localDateStr(d) {
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }

  // --------- Active fighter cutoff ---------
  cfl.activeCutoff = (function () {
    const d = new Date();
    d.setMonth(d.getMonth() - 24);
    return d.toISOString().slice(0, 10);
  })();

  // --------- URL helpers ---------
  cfl.fighterUrl = function (id) { return `fighter.html?id=${id}`; };
  cfl.eventUrl = function (id) { return `event.html?id=${id}`; };
  cfl.h2hUrl = function (aId, bId) {
    const params = new URLSearchParams();
    if (aId) params.set('a', aId);
    if (bId) params.set('b', bId);
    return `h2h.html?${params.toString()}`;
  };

  cfl.getQueryParam = function (key) {
    return new URLSearchParams(window.location.search).get(key);
  };

  // --------- Nav renderer ---------
  // Marks active link based on current page
  cfl.renderNav = function (active) {
    // DOM order matters on mobile: slot comes before burger so the flex layout
    // ends up [logo] ......... [slot][burger] with burger as the far-right tap
    // target (standard mobile pattern). The drawer is position:fixed so its
    // DOM position doesn't affect the bar layout.
    const navHtml = `
      <a class="cfl-logo" href="index.html">
        <span class="full">Cannon Fight <span class="accent">Lab</span></span>
        <span class="short">C<span class="accent">F</span>L</span>
      </a>
      <div class="cfl-nav-links" id="cflNavLinks">
        <a class="cfl-nav-cta-link ${active === 'home' || active === 'cardlab' ? 'active' : ''}" href="index.html#next">Card Lab</a>
        <a href="track-record.html" ${active === 'track' ? 'class="active"' : ''}>
          <span class="full">Track Record</span><span class="short">Record</span>
        </a>
        <a href="props.html" ${active === 'props' ? 'class="active"' : ''}>
          <span class="full">Prop Board</span><span class="short">Props</span>
        </a>
        <div class="cfl-nav-menu">
          <button type="button" class="cfl-nav-menu-btn ${['parlay','cardio','stats'].indexOf(active) !== -1 ? 'active' : ''}" aria-haspopup="true">Tools</button>
          <div class="cfl-nav-menu-panel">
            <a href="parlay.html" ${active === 'parlay' ? 'class="active"' : ''}>Parlay Builder</a>
            <a href="cardio.html" ${active === 'cardio' ? 'class="active"' : ''}>Cardio Scores</a>
            <a href="stats.html" ${active === 'stats' ? 'class="active"' : ''}>Factor Lab</a>
          </div>
        </div>
        <a href="pricing.html" ${active === 'pricing' ? 'class="active"' : ''}>Pricing</a>
      </div>
      <span class="cfl-nav-status" title="Model live"><span class="live-dot"></span>MODEL&nbsp;·&nbsp;LIVE</span>
      <div class="cfl-nav-slot" id="cflNavSlot"></div>
      <button class="cfl-nav-burger" id="cflNavBurger" aria-label="Menu" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>
    `;
    const navEl = document.querySelector('nav.cfl-nav');
    if (navEl) {
      navEl.innerHTML = navHtml;
      // Wire the auth slot once cflAuth is available. cflAuth handles its own
      // re-rendering on auth state change so we don't need to call this again.
      if (window.cflAuth) {
        const slot = document.getElementById('cflNavSlot');
        window.cflAuth.renderNavSlot(slot);
      }
      // Mobile drawer toggle
      const burger = document.getElementById('cflNavBurger');
      const links  = document.getElementById('cflNavLinks');
      if (burger && links) {
        burger.addEventListener('click', () => {
          const open = navEl.classList.toggle('cfl-nav-open');
          burger.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
        // Close on link tap (mobile)
        links.querySelectorAll('a').forEach(a => {
          a.addEventListener('click', () => {
            navEl.classList.remove('cfl-nav-open');
            burger.setAttribute('aria-expanded', 'false');
          });
        });
      }
    }
  };

  // --------- Footer renderer ---------
  cfl.renderFooter = function () {
    const footerHtml = `
      <div class="footer-logo">Cannon Fight <span class="accent">Lab</span></div>
      <div class="cfl-footer-text">Cannon Fight Lab is an analytics publication, not a sportsbook. Statistics describe historical patterns and do not predict individual fight outcomes. 21+ only. Problem gambling? Call 1-800-GAMBLER or the Tennessee REDLINE at 1-800-889-9789.</div>
      <div class="cfl-footer-links">
        <a href="about.html">About</a>
        <a href="contact.html">Contact</a>
        <a href="methodology.html">Methodology</a>
        <a href="disclaimer.html">Disclaimer</a>
        <a href="privacy.html">Privacy</a>
      </div>
    `;
    const footEl = document.querySelector('footer.cfl-footer');
    if (footEl) footEl.innerHTML = footerHtml;
  };

  // --------- Loading / error helpers ---------
  cfl.loadingHtml = function (msg) {
    return `<div class="loading-state"><div class="loading-spinner"></div><div>${cfl.escapeHtml(msg || 'Loading…')}</div></div>`;
  };

  cfl.errorHtml = function (msg) {
    return `<div class="error-state">${cfl.escapeHtml(msg)}</div>`;
  };

  // --------- Pagination helper for Supabase queries ---------
  // Use to grab >1000 rows, since Supabase caps per-call at 1000
  cfl.fetchAll = async function (queryBuilder) {
    let all = [];
    let from = 0;
    const pageSize = 1000;
    while (true) {
      const { data, error } = await queryBuilder().range(from, from + pageSize - 1);
      if (error) throw error;
      if (!data || data.length === 0) break;
      all = all.concat(data);
      if (data.length < pageSize) break;
      from += pageSize;
    }
    return all;
  };

  // --------- Fighter chip (compact representation) ---------
  cfl.fighterChip = function (fighter, opts) {
    opts = opts || {};
    const size = opts.size || 'md';
    const link = opts.link !== false;
    const inner = `
      <div class="cfl-avatar ${size}">${cfl.escapeHtml(cfl.initials(fighter.name))}</div>
      <div class="fighter-info">
        <div class="fighter-name">${cfl.escapeHtml(fighter.name)}</div>
        ${opts.subline ? `<div class="fighter-meta">${cfl.escapeHtml(opts.subline)}</div>` : ''}
      </div>
    `;
    if (link && fighter.id) {
      return `<a href="${cfl.fighterUrl(fighter.id)}" class="fighter-chip-link">${inner}</a>`;
    }
    return `<div class="fighter-chip">${inner}</div>`;
  };

  // --------- Traffic-funnel widgets ---------
  // Drop a signup CTA into any page:
  //   <div class="cfl-funnel-cta" data-source="fighters-bottom"></div>
  // …then call cfl.renderFunnelCtas() after the page loads. We auto-hide
  // each banner if the visitor is already signed in, so it never nags
  // existing users.
  cfl.renderFunnelCtas = function () {
    const els = document.querySelectorAll('.cfl-funnel-cta:not([data-cfl-rendered])');
    if (!els.length) return;
    const signedIn = window.cflAuth && window.cflAuth.isSignedIn && window.cflAuth.isSignedIn();
    els.forEach(el => {
      el.setAttribute('data-cfl-rendered', '1');
      if (signedIn) { el.style.display = 'none'; return; }
      const source = el.getAttribute('data-source') || 'inline';
      const headline = el.getAttribute('data-headline') || 'Free during beta — every edge factor unlocked.';
      const sub = el.getAttribute('data-sub') || 'Create a free account to track your picks, see every model verdict, and get the weekly preview email.';
      el.innerHTML = `
        <div class="cfl-funnel-cta-inner">
          <div class="cfl-funnel-cta-copy">
            <strong>${cfl.escapeHtml(headline)}</strong>
            <span>${cfl.escapeHtml(sub)}</span>
          </div>
          <div class="cfl-funnel-cta-actions">
            <a class="btn" href="/signup.html?src=${encodeURIComponent(source)}">Create free account →</a>
          </div>
        </div>
      `;
    });
    // Re-evaluate on auth change so the banner disappears immediately after
    // signup without a hard reload.
    if (window.cflAuth && window.cflAuth.onAuthChange) {
      window.cflAuth.onAuthChange((user) => {
        if (user) {
          document.querySelectorAll('.cfl-funnel-cta[data-cfl-rendered]').forEach(el => { el.style.display = 'none'; });
        }
      });
    }
  };

  // Email-only lead magnet. Drop:
  //   <div class="cfl-email-capture" data-source="home-footer"></div>
  // …then call cfl.renderEmailCaptures(). Submitting writes to the
  // email_subscribers table; the digest workflow picks it up from there.
  cfl.renderEmailCaptures = function () {
    const els = document.querySelectorAll('.cfl-email-capture:not([data-cfl-rendered])');
    els.forEach(el => {
      el.setAttribute('data-cfl-rendered', '1');
      const source = el.getAttribute('data-source') || 'inline';
      const headline = el.getAttribute('data-headline') || 'Weekly fight preview, free.';
      const sub = el.getAttribute('data-sub') || 'Get every upcoming UFC card with the model’s verdict in your inbox.';
      el.innerHTML = `
        <div class="cfl-email-capture-inner">
          <div class="cfl-email-capture-copy">
            <strong>${cfl.escapeHtml(headline)}</strong>
            <span>${cfl.escapeHtml(sub)}</span>
          </div>
          <form class="cfl-email-capture-form" novalidate>
            <input type="email" required placeholder="you@example.com" autocomplete="email" aria-label="Email address">
            <button type="submit">Subscribe</button>
          </form>
          <div class="cfl-email-capture-msg" aria-live="polite"></div>
        </div>
      `;
      const form = el.querySelector('form');
      const input = el.querySelector('input[type=email]');
      const btn = el.querySelector('button');
      const msg = el.querySelector('.cfl-email-capture-msg');
      form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        msg.textContent = '';
        msg.classList.remove('err', 'ok');
        if (!window.cflAuth || !window.cflAuth.subscribeEmail) {
          msg.classList.add('err');
          msg.textContent = 'Subscription is temporarily unavailable.';
          return;
        }
        btn.disabled = true;
        const originalLabel = btn.textContent;
        btn.textContent = 'Submitting…';
        const { error } = await window.cflAuth.subscribeEmail(input.value, source);
        btn.disabled = false;
        btn.textContent = originalLabel;
        if (error) {
          msg.classList.add('err');
          msg.textContent = error.message || 'Something went wrong. Try again.';
          return;
        }
        msg.classList.add('ok');
        msg.textContent = 'Subscribed. Check your inbox before the next card.';
        form.reset();
      });
    });
  };

  // Auto-render funnel widgets whenever the DOM is ready. Safe to call this
  // even on pages that don't include any widget elements — the queries return
  // empty NodeLists and short-circuit.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      cfl.renderFunnelCtas();
      cfl.renderEmailCaptures();
    });
  } else {
    setTimeout(() => { cfl.renderFunnelCtas(); cfl.renderEmailCaptures(); }, 0);
  }

  window.cfl = cfl;
})();
