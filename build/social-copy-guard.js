// The last line of defence on outbound social copy.
//
// D-011 took the forecast off every public surface on 2026-09-21. The social
// poster kept publishing it for three weeks anyway ("our model reads DUNCAN 50%
// over ALLEN", "BONFIM 50% over PRADO"), because its only guard was a stamp the
// generator applied to its own output. This checks the words instead of the
// stamp: if a piece of copy reads like a forecast, it is refused, whatever
// produced it and whatever it is labelled.
//
// Pure: no network, no file system. Used by build/social-post.js and pinned by
// tests/social-guard.test.js.

'use strict';

// Each pattern is a way the retired copy actually phrased a forecast, or a
// close cousin of one. Market facts ("consensus 62%", "best price +150") are
// not matched: they describe the market, not CFL's view of who wins.
const FORECAST_PATTERNS = [
  { name: 'our model',            re: /\bour\s+models?\b/i },
  { name: "model's read",         re: /\bmodel'?s\s+(read|pick|call|take)\b/i },
  { name: 'model reads / has it', re: /\bmodels?\s+(reads?|has\s+it|likes?|picks?|says|favou?rs?|backs?)\b/i },
  { name: 'NN% over NAME',        re: /\b\d{1,3}\s?%\s+over\s+\S/i },
  { name: 'win probability',      re: /\bwin\s+(probability|chance)\b/i },
  { name: 'pick / lock / bet',    re: /\b(our|cfl'?s?|the)\s+(pick|lock|best\s+bet|play)\b/i },
  { name: 'value / edge claim',   re: /\b(value\s+(bet|play|side)|edge\s+on|beats?\s+the\s+(market|close|closing\s+line|opener))\b/i },
  { name: 'fade',                 re: /\bfade\s+(candidate|him|her|them|this)\b/i },
];

// Returns the name of the first forecast pattern the text matches, or null.
function forecastClaim(text) {
  const s = String(text || '');
  for (const p of FORECAST_PATTERNS) if (p.re.test(s)) return p.name;
  return null;
}

module.exports = { forecastClaim, FORECAST_PATTERNS };
