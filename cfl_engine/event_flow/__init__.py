"""Event flow: what order a card's bouts run in, captured as observations.

`ufcstats_card` parses a UFCStats event page. `bout_order` turns a parsed page
into ledger rows. `ingest_bout_order` is the runner that writes them.

Nothing here computes an order. The page states one; we record what it said and
when we looked.
"""
