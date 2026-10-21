/* ==========================================================================
   entitlements.js — the Free/Pro boundary, and the gate on turning checkout on.

   Two jobs, both of them about making a decision impossible to take by
   accident:

     1. THE BOUNDARY. One list of which surfaces are free and which are Pro,
        so `PRODUCT_BOUNDARY.md` and the code cannot drift. Nothing here
        enforces anything yet — applying the boundary is a later step, and the
        enforcement will be in Postgres (`current_user_is_pro()`), not here.

     2. THE CHECKOUT GATE. Two compliance items must be resolved before CFL
        takes a payment. Writing that in a document did not feel like enough,
        because the sprint that builds Stripe is the sprint most likely to
        forget it. So it is a constant, a function, and a test that fails.

   WHY THE GATE IS CODE AND NOT A NOTE

   `CHECKOUT_BLOCKERS` is not advisory. `checkoutMayBeEnabled()` returns false
   while any blocker is unresolved, and `tests/entitlements.test.js` fails if
   a checkout entry point ships while it does. To turn checkout on, someone has
   to delete a named legal blocker from this file — which is a deliberate act
   with a reviewer attached, rather than a default that slips through.

   ENFORCEMENT, STATED ONCE: THIS FILE IS PRESENTATION ONLY.

   Everything in it runs on the reader's machine. It decides what to DRAW. It
   never decides what may be SENT. A Pro surface is gated by a
   Postgres policy or a definer view calling `current_user_is_pro()`. The
   publishable key is public by design, so a gate that exists only here is not
   a gate at all.
   ========================================================================== */
(function () {
  'use strict';

  const E = {};

  // ---------------------------------------------------------------- blockers
  // Each entry blocks CHECKOUT, not the build. Auth, entitlements, pricing
  // pages and Stripe wiring may all be built and tested while these stand —
  // only taking real money is blocked. Remove an entry when the item is
  // genuinely resolved, never to make a test pass.
  E.CHECKOUT_BLOCKERS = [
    {
      id: 'T-054',
      what: 'the privacy policy has not had legal review',
      why: 'Corrected 2026-10-21 (owner-approved A1): it now names Plausible ' +
           'and drops the false cookie, affiliate and IP claims. The owner ' +
           'kept payments blocked until a lawyer has reviewed it.',
      owner: 'Owner + lawyer',
      draft: 'legal-review/PROPOSED_WORDING.md'
    },
    {
      id: 'T-048',
      what: 'no Terms of Service page exists',
      why: 'A subscription needs terms: billing period, renewal, cancellation, ' +
           'refunds, limitation of liability. None of it is decided and none ' +
           'of it is ours to decide.',
      owner: 'Owner + lawyer',
      draft: 'legal-review/PROPOSED_WORDING.md'
    }
  ];

  E.checkoutMayBeEnabled = function () {
    return E.CHECKOUT_BLOCKERS.length === 0;
  };

  E.checkoutBlockerSummary = function () {
    if (E.checkoutMayBeEnabled()) return 'No blockers recorded.';
    return E.CHECKOUT_BLOCKERS
      .map(b => b.id + ' — ' + b.what + ' (' + b.owner + ')')
      .join('; ');
  };

  // ---------------------------------------------------------------- boundary
  // Mirrors PRODUCT_BOUNDARY.md. `tests/entitlements.test.js` checks the two
  // agree, so the document cannot quietly become fiction.
  //
  // `enforced` is false on every row today, deliberately: this sprint builds
  // the machinery and gates nothing. When a row flips to true, the gate must
  // already exist in Postgres — the test checks that too.
  E.SURFACES = [
    // free, and staying free: the facts
    { key: 'card_lab',        tier: 'free', enforced: false, what: 'the current card, every fight' },
    { key: 'market_lab',      tier: 'free', enforced: false, what: 'the board: consensus, best price, spread' },
    { key: 'fight_lab',       tier: 'free', enforced: false, what: 'one matchup in full' },
    { key: 'factor_lab',      tier: 'free', enforced: false, what: 'every finding, sample size and verdict' },
    { key: 'fighter_pages',   tier: 'free', enforced: false, what: 'all ~4,500' },
    { key: 'event_pages',     tier: 'free', enforced: false, what: 'all ~800' },
    { key: 'proof_center',    tier: 'free', enforced: false, what: 'including the failures' },
    { key: 'model_archive',   tier: 'free', enforced: false, what: 'the retired forecast’s whole record — evidence, not a feature' },
    { key: 'card_brief',      tier: 'free', enforced: false, what: 'signup and delivery' },
    { key: 'movement_headline', tier: 'free', enforced: false, what: 'the move since first broad capture, with its cohort' },
    { key: 'best_price',      tier: 'free', enforced: false, what: 'best observed price, its book and its age' },

    // pro: depth, history, monitoring, personalisation — never facts
    { key: 'movement_chart_history', tier: 'pro', enforced: false, what: 'the full plotted series rather than the headline' },
    { key: 'book_by_book_history',   tier: 'pro', enforced: false, what: 'every sportsbook’s own history, not just its current price' },
    { key: 'historical_lookback',    tier: 'pro', enforced: false, what: 'past cards beyond the current window' },
    { key: 'watchlists',             tier: 'pro', enforced: false, what: 'fights and fighters a reader follows' },
    { key: 'price_alerts',           tier: 'pro', enforced: false, what: '“tell me if anyone posts +150”' },
    { key: 'movement_alerts',        tier: 'pro', enforced: false, what: '“tell me if this moves 3+ points”' },
    { key: 'since_last_visit',       tier: 'pro', enforced: false, what: 'what changed since the reader was last here' },
    { key: 'advanced_matchup',       tier: 'pro', enforced: false, what: 'the deeper per-fight breakdowns' }
  ];

  // Never sold, at any tier. The list exists so a pricing page cannot invent
  // a feature the product has spent a sprint removing.
  E.NEVER_SOLD = [
    'picks', 'plays', 'best bets', 'leans', 'locks', 'a recommended side',
    'a CFL win probability presented as something to bet into',
    'an edge percentage', 'an expected-value figure', 'a staking suggestion',
    'any claim that CFL beats the market or that a reader will profit',
    'affiliate placement dressed as a recommendation'
  ];

  // ------------------------------------------------------------ server gates
  // Where each Pro surface WOULD be enforced, once T-061 is approved. Drafted,
  // not applied: research/commercial/t061_pro_gates.DRAFT.sql holds the SQL,
  // and tests/test_t061_pro_gates_sql.py runs it on a throwaway Postgres.
  //
  // This is a pointer, not a gate. Every entry names an object that calls
  // current_user_is_pro() in Postgres; nothing here is consulted to decide
  // what data is sent. `not_built` means there is no table or view behind the
  // surface yet, so there is nothing to gate and it must stay unenforced.
  E.PRO_GATES_DRAFT_FILE = 'research/commercial/t061_pro_gates.DRAFT.sql';
  E.PRO_GATES_DRAFT = {
    movement_chart_history: { kind: 'view',     object: 'v_pro_fight_chart_series',
                              replaces: 'v_fight_chart_series' },
    book_by_book_history:   { kind: 'view',     object: 'v_pro_fight_chart_books',
                              replaces: 'v_fight_chart_books' },
    historical_lookback:    { kind: 'view',     object: 'v_fight_market_movement_lookback',
                              replaces: null },
    watchlists:             { kind: 'policy',   object: 'watchlist insert own (pro)',
                              replaces: 'watchlist insert own' },
    price_alerts:           { kind: 'function', object: 'alert_quota',
                              replaces: null },
    movement_alerts:        { kind: 'function', object: 'alert_quota',
                              replaces: null },
    since_last_visit:       { kind: 'not_built', object: null, replaces: null },
    advanced_matchup:       { kind: 'not_built', object: null, replaces: null }
  };

  // ------------------------------------------------------------------- plans
  // What CFL Pro would be sold as. EVERY AMOUNT IS NULL, on purpose: the price
  // is T-067, an owner decision (CRITICAL_GATES item 7), and it is not set.
  // pricing.html renders from this list, so the page can only say what is
  // true: "price not set". Nothing on any page may hardcode an amount;
  // tests/pricing-config.test.js fails if one appears.
  //
  // To set a price: put the amount here in CENTS, as an integer, in the same
  // pull request that creates the Stripe price it describes (T-068). The
  // Stripe price is what charges; this only describes it to the reader, so
  // the two must agree.
  E.PRICE_DECISION = 'T-067';
  E.PLANS = [
    { id: 'pro_monthly', label: 'Monthly', interval: 'month',
      amount_cents: null, currency: 'usd',
      stripe_price_secret: 'STRIPE_PRICE_ID' },
    { id: 'pro_yearly',  label: 'Yearly',  interval: 'year',
      amount_cents: null, currency: 'usd',
      // The checkout function reads ONE price id today. Selling a second
      // period needs the function to accept a plan id and map it to a second
      // secret — a code change, decided at T-067, not a config flip.
      stripe_price_secret: null }
  ];

  E.priceIsSet = function (plan) {
    return !!plan && Number.isInteger(plan.amount_cents) && plan.amount_cents > 0;
  };

  // The line a reader sees for one plan. Never guesses, never rounds a missing
  // price into a range, never says "from".
  E.priceLabel = function (plan) {
    if (!E.priceIsSet(plan)) return 'Price not set';
    const dollars = (plan.amount_cents / 100).toFixed(2);
    const sym = plan.currency === 'usd' ? '$' : (String(plan.currency).toUpperCase() + ' ');
    return sym + dollars + ' / ' + plan.interval;
  };

  E.planRows = function () {
    return E.PLANS.map(p => ({ id: p.id, label: p.label, price: E.priceLabel(p), set: E.priceIsSet(p) }));
  };

  E.tierFor = function (key) {
    const row = E.SURFACES.filter(s => s.key === key)[0];
    return row ? row.tier : null;
  };

  // What the UI should show for a surface, given who is asking. Returns the
  // render decision only — the data still has to survive the server.
  E.decide = function (key, isPro) {
    const tier = E.tierFor(key);
    if (tier === null) return { show: true, reason: 'unknown_surface' };
    if (tier === 'free') return { show: true, reason: 'free' };
    return isPro
      ? { show: true, reason: 'pro_entitled' }
      : { show: false, reason: 'pro_required' };
  };

  const api = E;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflEntitlements = api;
})();
