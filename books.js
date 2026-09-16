/* ==========================================================================
   Cannon Fight Lab — sportsbook registry
   --------------------------------------------------------------------------
   Which books the site may show as a price you can actually take, and which
   only feed the consensus maths. Shared by the browser (window.cflBooks) and
   the build (require('../books')).

   Rules (September 2026):
     * Only books licensed by the Tennessee Sports Wagering Council are shown
       as purchasable prices, get a plain homepage link and can carry the
       "best price" label.
     * Offshore books feed the vig-free consensus but never get a link or a
       "best price" label.
     * Prediction markets (Polymarket, Kalshi) and CFL's own synthetic
       consensus row are not sportsbooks and are excluded from the market
       number entirely — mirrored in fight_week_views.sql
       (v_odds_books_sportsbooks). Keep the two lists in step.
     * No affiliate codes, ever. Links are the book's public front door.

   The Tennessee list is copied from the regulator's page (source + check date
   are in TN_LIST_CHECKED / TN_LIST_SOURCE below and shown on the Market
   Board). An unlisted book is treated as not purchasable, which can only ever
   hide a price, never show a wrong one. Reed maintains this list.
   ========================================================================== */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.cflBooks = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // Not sportsbooks. Excluded from the consensus (see the SQL view).
  const SPORTSBOOK_EXCLUDE = ['polymarket', 'kalshi'];
  const SYNTHETIC_MATCH = /consensus/i;

  // Tennessee-licensed online sportsbooks.
  // SOURCE: Tennessee Sports Wagering Council, "Licensees & Registrants",
  //   https://www.tn.gov/content/tn/swac/licensees-registrants.html
  // CHECKED: 2026-09-16 (Reed + Claude). Nine licensed operators on that date:
  //   Caesars, Bally Bet, FanDuel, BetMGM, DraftKings, Fanatics, bet365,
  //   theScore Bet, Hard Rock Bet. BetRivers is NOT on the list.
  // Re-check the page when a book appears in odds_books that is not here, and
  // update TN_LIST_CHECKED so the date on the Market Board stays honest.
  const TN_LIST_CHECKED = '2026-09-16';
  const TN_LIST_SOURCE = 'https://www.tn.gov/content/tn/swac/licensees-registrants.html';
  // Keys are lower-cased odds_books.name (add aliases as the feed introduces them).
  const TN_LICENSED = {
    'caesars':      { label: 'Caesars',       url: 'https://sportsbook.caesars.com/' },
    'bally bet':    { label: 'Bally Bet',     url: 'https://www.ballybet.com/' },
    'ballybet':     { label: 'Bally Bet',     url: 'https://www.ballybet.com/' },
    'fanduel':      { label: 'FanDuel',       url: 'https://sportsbook.fanduel.com/' },
    'betmgm':       { label: 'BetMGM',        url: 'https://sports.tn.betmgm.com/' },
    'draftkings':   { label: 'DraftKings',    url: 'https://sportsbook.draftkings.com/' },
    'fanatics':     { label: 'Fanatics',      url: 'https://sportsbook.fanatics.com/' },
    'bet365':       { label: 'bet365',        url: 'https://www.bet365.com/' },
    'thescore bet': { label: 'theScore Bet',  url: 'https://thescore.bet/' },
    'thescorebet':  { label: 'theScore Bet',  url: 'https://thescore.bet/' },
    'hard rock bet':{ label: 'Hard Rock Bet', url: 'https://www.hardrock.bet/' },
    'hardrockbet':  { label: 'Hard Rock Bet', url: 'https://www.hardrock.bet/' },
  };

  function key(name) { return String(name || '').trim().toLowerCase(); }

  function isSportsbook(name) {
    const k = key(name);
    return !!k && !SYNTHETIC_MATCH.test(k) && SPORTSBOOK_EXCLUDE.indexOf(k) === -1;
  }
  function isLicensed(name) { return !!TN_LICENSED[key(name)]; }
  function info(name) { return TN_LICENSED[key(name)] || null; }
  // Plain front-door link for a licensed book; null for everything else.
  function link(name) { const i = info(name); return i ? i.url : null; }
  function label(name) { const i = info(name); return i ? i.label : String(name || ''); }

  return { SPORTSBOOK_EXCLUDE, TN_LICENSED, TN_LIST_CHECKED, TN_LIST_SOURCE, isSportsbook, isLicensed, info, link, label };
});
