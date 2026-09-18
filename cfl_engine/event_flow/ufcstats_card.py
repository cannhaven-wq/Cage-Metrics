"""Parse a UFCStats event page into its bouts, in the order the page lists them.

Plain English
-------------
UFCStats publishes each card as one table, main event at the top, first prelim
at the bottom. That table is the only free, public statement of what order a
card actually runs in. This module reads it and nothing else — it does no
matching, no database work, and no guessing.

What it returns
---------------
A list of `PageBout`, in page order (index 0 = the top row = the main event).
Each carries the UFCStats fight id lifted from the row's `data-link`, the two
fighter names as printed, and its row index.

What it refuses
---------------
Anything it cannot read exactly. A row with no `data-link`, a fight id that is
not a 16-character hex token, a row that does not print two fighters, or a page
whose fight ids repeat — each raises `CardParseError`. A card's running order is
positional: one silently dropped row shifts the number on every bout below it.
So a page that is partly unreadable is not partly usable.

No HTML library is imported. The repo's Python has no bs4 dependency and this
parser has one job, so it uses `html.parser` from the standard library.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

# UFCStats ids are 16 lowercase hex characters. Anything else is not an id we
# recognise, and guessing at one would mean linking a price to the wrong bout.
FIGHT_ID_RE = re.compile(r"/fight-details/([0-9a-f]{16})\b")
EVENT_ID_RE = re.compile(r"/event-details/([0-9a-f]{16})\b")
FIGHTER_ID_RE = re.compile(r"/fighter-details/([0-9a-f]{16})\b")


class CardParseError(Exception):
    """The page could not be read exactly. Never downgraded to a warning."""


@dataclass(frozen=True)
class PageBout:
    """One row of the event table, exactly as the page printed it."""

    page_index: int                 # 0 = top row = main event
    ufc_fight_id: str
    fighter_names: tuple[str, ...]  # in the order the row printed them
    ufc_fighter_ids: tuple[str, ...]

    @property
    def matchup(self) -> str:
        return " vs ".join(self.fighter_names)


@dataclass(frozen=True)
class ParsedCard:
    ufc_event_id: str | None
    bouts: tuple[PageBout, ...]

    def __len__(self) -> int:
        return len(self.bouts)


class _CardParser(HTMLParser):
    """Collect one record per table row carrying a fight-details data-link.

    UFCStats marks each bout row with `data-link="…/fight-details/<id>"`, and
    prints the two corners as `…/fighter-details/<id>` anchors inside it. Those
    two facts are the whole contract this parser depends on; both are asserted
    by the tests, and a page that stops honouring either raises rather than
    returning a shorter card.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._row: dict | None = None
        self._depth = 0
        self._in_fighter_link = False
        self._text: list[str] = []

    # -- rows ---------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            link = a.get("data-link", "")
            m = FIGHT_ID_RE.search(link)
            if m:
                self._row = {"ufc_fight_id": m.group(1), "names": [], "fighter_ids": []}
                self._depth = 1
                return
            if self._row is not None:
                # A nested <tr> inside a bout row would make "which row am I in"
                # ambiguous. UFCStats does not nest them; if that changes we
                # stop rather than mis-assign a fighter to the wrong bout.
                raise CardParseError("nested <tr> inside a bout row")
        if self._row is None:
            return
        if tag == "a":
            m = FIGHTER_ID_RE.search(a.get("href", ""))
            if m:
                self._in_fighter_link = True
                self._text = []
                self._row["fighter_ids"].append(m.group(1))

    def handle_endtag(self, tag):
        if self._row is None:
            return
        if tag == "a" and self._in_fighter_link:
            self._in_fighter_link = False
            self._row["names"].append(" ".join("".join(self._text).split()))
            self._text = []
        elif tag == "tr":
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._in_fighter_link:
            self._text.append(data)


def parse_event_page(html: str) -> ParsedCard:
    """Read a UFCStats event page. Raises `CardParseError` on anything unclear."""
    if not html or not html.strip():
        raise CardParseError("empty page")

    parser = _CardParser()
    parser.feed(html)
    parser.close()

    if parser._row is not None:
        # A bout row that never closed would be dropped, and a dropped row does
        # not produce a missing bout — it produces a SHORTER card, which
        # renumbers every bout and looks entirely plausible. Truncated HTML is
        # the likeliest cause, and it is exactly the failure this whole module
        # is built to refuse.
        raise CardParseError(
            f"the page ended inside bout row {parser._row['ufc_fight_id']} — "
            f"truncated response; refusing to read a short card"
        )

    if not parser.rows:
        raise CardParseError(
            "no bout rows found — the page carries no data-link fight rows. "
            "Either the card is not posted yet or the markup changed."
        )

    bouts: list[PageBout] = []
    for i, row in enumerate(parser.rows):
        names = [n for n in row["names"] if n]
        if len(names) != 2:
            raise CardParseError(
                f"row {i} (fight {row['ufc_fight_id']}) printed {len(names)} "
                f"fighter names, expected 2"
            )
        if len(row["fighter_ids"]) != 2:
            raise CardParseError(
                f"row {i} (fight {row['ufc_fight_id']}) carried "
                f"{len(row['fighter_ids'])} fighter links, expected 2"
            )
        bouts.append(
            PageBout(
                page_index=i,
                ufc_fight_id=row["ufc_fight_id"],
                fighter_names=tuple(names),
                ufc_fighter_ids=tuple(row["fighter_ids"]),
            )
        )

    seen: set[str] = set()
    for b in bouts:
        if b.ufc_fight_id in seen:
            raise CardParseError(
                f"fight id {b.ufc_fight_id} appears twice on the page — "
                f"the running order cannot be read unambiguously"
            )
        seen.add(b.ufc_fight_id)

    m = EVENT_ID_RE.search(html)
    return ParsedCard(ufc_event_id=m.group(1) if m else None, bouts=tuple(bouts))
