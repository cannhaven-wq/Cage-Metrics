/* ==========================================================================
   build/promotion.js — T-086. Is this card a UFC event?

   One rule, decided on the event name, used wherever a card has to be told
   apart from Dana White's Contender Series, Road to UFC or anything else.

   The same rule exists in three other places, and they must agree:
     * t086_dwcs_non_ufc.sql             the events_ufc_name_only CHECK;
     * cfl_engine/integrity/checks.py    non_ufc_card_in_events;
     * research/data-integrity/reconcile_ufc_records.py  UFC_EVENT_RE;
   plus the event scraper (cage-metrics-event-scrapper/promotion.py).
   tests/promotion-rule.test.js runs one list of names through the JS, SQL
   and Python copies and fails if any disagree.

   UFC  = a name containing the word "UFC" (UFC 300, UFC Fight Night, Noche
          UFC, UFC Freedom 250), "The Ultimate Fighter ..." or the 2006 card
          "Ortiz vs Shamrock 3" — but never "Road to UFC ...".
   ========================================================================== */
'use strict';

const UFC_NAME = /(^|[^A-Za-z0-9_])UFC(?![A-Za-z0-9_])|^The Ultimate Fighter(?![A-Za-z0-9_])|^Ortiz vs\.? Shamrock 3(?![A-Za-z0-9_])/;
const ROAD_TO_UFC = /^\s*road to ufc/i;

function isUfcEventName(name) {
  const s = String(name || '');
  return UFC_NAME.test(s) && !ROAD_TO_UFC.test(s);
}

// The label stored in events_non_ufc.promotion for a card that is not UFC.
function nonUfcPromotion(name) {
  const s = String(name || '');
  if (/^\s*(dwcs\b|dana white.?s contender series)/i.test(s)) return 'DWCS';
  if (ROAD_TO_UFC.test(s)) return 'RTU';
  return 'OTHER';
}

// Plain-English name for a page.
const PROMOTION_LABEL = {
  DWCS: "Dana White's Contender Series",
  RTU: 'Road to UFC',
  OTHER: 'a non-UFC promotion',
};

module.exports = { isUfcEventName, nonUfcPromotion, PROMOTION_LABEL };
