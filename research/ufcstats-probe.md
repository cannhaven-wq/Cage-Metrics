# ufcstats probe
Generated: 2026-05-30T17:00:35.141Z

## Supabase event 113
[
  {
    "id": 113,
    "name": "UFC Fight Night: Song vs. Figueiredo",
    "event_date": "2026-05-30",
    "is_upcoming": true,
    "ufc_url": "http://www.ufcstats.com/event-details/1e75e6c9de99fa76"
  }
]

## GET http://www.ufcstats.com/statistics/events/upcoming
HTTP 200, 2994 bytes
event-details links found: 0

contains 'b-statistics__table-row': false
contains 'b-link_style_black': false
looks like a block/challenge page: false

## GET http://www.ufcstats.com/statistics/events/completed?page=1
HTTP 200, 2994 bytes
event-details links found: 0

contains 'b-statistics__table-row': false
contains 'b-link_style_black': false
looks like a block/challenge page: false

## Macau event not found in completed page 1 (parser may be matching nothing, or ufcstats hasn't posted it).
