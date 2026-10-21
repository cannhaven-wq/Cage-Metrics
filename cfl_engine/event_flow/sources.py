"""Running-order sources behind one interface, so a raw source can be swapped.

Plain English
-------------
CFL needs one fact per bout: where it sits in the order the card walks out.
UFCStats was the only source the ingester knew, and UFCStats does not answer
GitHub's runners (it serves them an anti-bot page). This module puts every
candidate source behind the same small shape — a card, first walkout first —
so the ingester, the real-page check and any cross-check read them the same
way and a source can be replaced without touching the ledger logic.

    SourceCard(source, event_name, bouts=(SourceBout(walkout=1, ...), ...))

Adapters
--------
* `from_ufcstats(parsed)` — the existing UFCStats parser; the page lists the
  main event FIRST, so it is reversed here (the flip lives in one place).
* `parse_espn_scoreboard(data)` — ESPN's public MMA scoreboard JSON
  (site.web.api.espn.com). It lists competitions FIRST WALKOUT FIRST, verified
  2026-10-21 on UFC Fight Night: Buckley vs. Malott, where the last
  competition is the main event the card is named after. Each competition
  carries the start time of its card section, which must never decrease along
  the order; a card where it does is refused, because then the array is not a
  running order.
* `parse_wikipedia_results(wikitext)` — the "Results" table of the event's
  English Wikipedia article (MediaWiki API). Community-edited, so it is used to
  CROSS-CHECK another source, never on its own.

What every adapter refuses
--------------------------
A bout without exactly two fighter names, an empty card, or anything it cannot
read exactly. A running order is positional: a silently dropped bout renumbers
every bout after it.

The trimming helpers (`espn_fixture`, `wikipedia_results_section`) cut a raw
response down to the fields the adapters read, without changing any value. The
test fixtures in `fixtures/` were produced by them from real responses, and the
raw response's sha256 is recorded beside each one.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

UFCSTATS = "ufcstats_card"
ESPN = "espn_scoreboard"
WIKIPEDIA = "wikipedia"


class SourceError(Exception):
    """The source could not be read exactly. Never downgraded to a warning."""


@dataclass(frozen=True)
class SourceBout:
    walkout: int                        # 1 = first bout to walk out
    fighter_names: tuple[str, str]
    source_bout_id: str                 # UFCStats fight id, ESPN competition id, wiki row
    section_start: str | None = None    # ISO instant the source gives for this bout's section
    weight_class: str | None = None

    @property
    def matchup(self) -> str:
        return " vs ".join(self.fighter_names)


@dataclass(frozen=True)
class SourceCard:
    source: str
    source_event_id: str | None
    event_name: str | None
    event_date: str | None
    bouts: tuple[SourceBout, ...]       # first walkout first

    @property
    def main_event(self) -> SourceBout:
        return self.bouts[-1]

    @property
    def first_walkout(self) -> SourceBout:
        return self.bouts[0]


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------
def fold(text: str) -> str:
    """'José  Aldo Jr.' -> 'jose aldo jr'. Accents, case and punctuation never decide."""
    nfkd = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", plain.lower().replace("'", "")).split())


def compact(text: str) -> str:
    """'SuYoung You' and 'Su Young You' are one name; spacing never decides."""
    return fold(text).replace(" ", "")


def same_pair(a: tuple[str, str], b: tuple[str, str]) -> bool:
    x, y = sorted(compact(n) for n in a), sorted(compact(n) for n in b)
    return x == y


# ---------------------------------------------------------------------------
# UFCStats
# ---------------------------------------------------------------------------
def from_ufcstats(parsed, event_name: str | None = None,
                  event_date: str | None = None) -> SourceCard:
    """UFCStats lists the main event first; the ledger counts first walkout first."""
    n = len(parsed.bouts)
    if n == 0:
        raise SourceError("the UFCStats page listed no bouts")
    bouts = tuple(
        SourceBout(walkout=n - b.page_index, fighter_names=tuple(b.fighter_names),
                   source_bout_id=b.ufc_fight_id)
        for b in reversed(parsed.bouts)
    )
    return SourceCard(UFCSTATS, parsed.ufc_event_id, event_name, event_date, bouts)


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------
def espn_fixture(data: dict) -> dict:
    """A raw ESPN scoreboard, cut to what `parse_espn_scoreboard` reads.

    No value is changed; keys the adapter does not read are dropped so a real
    response can live in the repo as a small fixture.
    """
    def athlete(c):
        a = c.get("athlete") or {}
        return {"order": c.get("order"), "athlete": {"displayName": a.get("displayName")}}

    def competition(c):
        return {"id": c.get("id"), "date": c.get("date"), "startDate": c.get("startDate"),
                "type": {"abbreviation": (c.get("type") or {}).get("abbreviation")},
                "status": {"type": {"name": ((c.get("status") or {}).get("type") or {}).get("name")}},
                "competitors": [athlete(x) for x in c.get("competitors", [])]}

    leagues = data.get("leagues") or [{}]
    return {
        "leagues": [{"calendar": [
            {"label": c.get("label"), "startDate": c.get("startDate")}
            if isinstance(c, dict) else c
            for c in (leagues[0].get("calendar") or [])]}],
        "events": [{"id": e.get("id"), "name": e.get("name"), "date": e.get("date"),
                    "competitions": [competition(c) for c in e.get("competitions", [])]}
                   for e in data.get("events", [])],
    }


def parse_espn_scoreboard(data: dict) -> list[SourceCard]:
    """Every event on an ESPN scoreboard as a SourceCard, first walkout first."""
    cards = []
    for e in data.get("events") or []:
        comps = e.get("competitions") or []
        if not comps:
            raise SourceError(f"ESPN event {e.get('id')} lists no competitions")
        bouts, last_start = [], ""
        for i, c in enumerate(comps):
            competitors = sorted(c.get("competitors") or [],
                                 key=lambda x: (x.get("order") is None, x.get("order")))
            names = tuple(((x.get("athlete") or {}).get("displayName") or "").strip()
                          for x in competitors)
            if len(names) != 2 or not all(names):
                raise SourceError(f"ESPN competition {c.get('id')} on event {e.get('id')} "
                                  f"does not name two fighters: {names}")
            start = c.get("startDate") or c.get("date") or ""
            if start and last_start and start < last_start:
                raise SourceError(
                    f"ESPN event {e.get('id')}: competition {i} starts {start}, before the "
                    f"one listed ahead of it ({last_start}). The list is not a running order.")
            last_start = start or last_start
            bouts.append(SourceBout(walkout=i + 1, fighter_names=names,
                                    source_bout_id=str(c.get("id")), section_start=start or None,
                                    weight_class=(c.get("type") or {}).get("abbreviation")))
        cards.append(SourceCard(ESPN, str(e.get("id")), e.get("name"),
                                (e.get("date") or "")[:10] or None, tuple(bouts)))
    return cards


def espn_completed_dates(data: dict, before_iso: str) -> list[str]:
    """Event dates (YYYYMMDD) in the scoreboard's league calendar before an instant."""
    cal = ((data.get("leagues") or [{}])[0].get("calendar")) or []
    out = []
    for c in cal:
        start = c.get("startDate") if isinstance(c, dict) else c
        if start and start < before_iso:
            out.append(start[:10].replace("-", ""))
    return sorted(set(out))


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------
RESULTS_HEADING = re.compile(r"^==\s*(Results|Fight card)\s*==\s*$", re.M | re.I)
NEXT_HEADING = re.compile(r"^==[^=].*==\s*$", re.M)
BOUT_TEMPLATE = re.compile(r"\{\{\s*MMAevent bout\s*\|(.*?)\}\}", re.S | re.I)
LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")


def wikipedia_results_section(wikitext: str) -> str:
    """The article's Results (or Fight card) section, verbatim."""
    m = RESULTS_HEADING.search(wikitext)
    if not m:
        raise SourceError("the article has no Results / Fight card section")
    rest = wikitext[m.start():]
    nxt = NEXT_HEADING.search(rest, m.end() - m.start())
    return rest[: nxt.start()] if nxt else rest


def _plain(cell: str) -> str:
    cell = LINK.sub(lambda m: m.group(1), cell)
    cell = re.sub(r"\{\{[^{}]*\}\}", "", cell)
    cell = re.sub(r"<[^>]+>", "", cell)
    cell = re.sub(r"\([^)]*\)", "", cell)          # "(c)" champion markers
    return " ".join(cell.replace("'''", "").split())


def parse_wikipedia_results(wikitext: str, event_name: str | None = None) -> SourceCard:
    """Wikipedia lists the main event first (main card, then prelims); reversed here."""
    section = wikipedia_results_section(wikitext)
    rows = []
    for m in BOUT_TEMPLATE.finditer(section):
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 4:
            raise SourceError(f"a bout row has {len(cells)} cells: {m.group(0)[:80]!r}")
        weight, a, _verb, b = cells[0], _plain(cells[1]), cells[2], _plain(cells[3])
        if not a or not b:
            raise SourceError(f"a bout row does not name two fighters: {m.group(0)[:80]!r}")
        rows.append((weight, a, b))
    if not rows:
        raise SourceError("the Results section lists no bouts")
    n = len(rows)
    bouts = tuple(
        SourceBout(walkout=n - i, fighter_names=(a, b), source_bout_id=f"row{i}",
                   weight_class=w)
        for i, (w, a, b) in reversed(list(enumerate(rows)))
    )
    return SourceCard(WIKIPEDIA, None, event_name, None, bouts)


# ---------------------------------------------------------------------------
# Checks shared by the real-page check and the ingester
# ---------------------------------------------------------------------------
def title_matchup(title: str | None) -> tuple[str, str] | None:
    """'UFC Fight Night: Buckley vs. Malott' -> ('buckley', 'malott')."""
    if not title:
        return None
    tail = title.split(":", 1)[1] if ":" in title else title
    parts = re.split(r"\s+vs\.?\s+", tail, flags=re.I)
    if len(parts) != 2:
        return None
    a, b = (fold(p) for p in parts)
    return (a, b) if a and b else None


def _surname_in(side: str, name: str) -> bool:
    full = fold(name)
    return bool(side) and (full == side or full.endswith(" " + side))


def bout_is_titled(names: tuple[str, str], matchup: tuple[str, str]) -> bool:
    a, b = matchup
    return ((_surname_in(a, names[0]) and _surname_in(b, names[1]))
            or (_surname_in(a, names[1]) and _surname_in(b, names[0])))


def direction(card: SourceCard) -> tuple[str, str]:
    """Is the main event the card is named after LAST in walkout order?"""
    m = title_matchup(card.event_name)
    if m is None:
        return "unconfirmable", "the event name carries no 'A vs. B' matchup"
    last, first = card.main_event, card.first_walkout
    if bout_is_titled(last.fighter_names, m) and not (
            len(card.bouts) > 1 and bout_is_titled(first.fighter_names, m)):
        return "confirmed", (f"the card is named after {last.matchup!r}, which is bout "
                             f"{last.walkout} of {len(card.bouts)} (last to walk out)")
    if len(card.bouts) > 1 and bout_is_titled(first.fighter_names, m):
        return "contradicted", (f"the card is named after {first.matchup!r}, which this "
                                f"source puts FIRST — the order is backwards")
    return "unconfirmable", "the titled matchup is neither first nor last"


def compare_orders(a: SourceCard, b: SourceCard) -> dict:
    """Bout-by-bout agreement between two sources, matched by fighter pair."""
    b_pos = {}
    for bout in b.bouts:
        b_pos[tuple(sorted(compact(n) for n in bout.fighter_names))] = bout.walkout
    rows, only_a = [], []
    for bout in a.bouts:
        key = tuple(sorted(compact(n) for n in bout.fighter_names))
        if key in b_pos:
            rows.append((bout.walkout, b_pos.pop(key), bout.matchup))
        else:
            only_a.append(bout.matchup)
    only_b = [x.matchup for x in b.bouts
              if tuple(sorted(compact(n) for n in x.fighter_names)) in b_pos]
    # Same relative order over the shared bouts?
    shared_b = [r[1] for r in rows]
    same_order = shared_b == sorted(shared_b)
    return {"shared": len(rows), "only_in_" + a.source: only_a, "only_in_" + b.source: only_b,
            "same_relative_order": same_order,
            "disagreements": [r[2] for r in rows if r[0] != r[1]]}


# ---------------------------------------------------------------------------
# Linking a source that carries no UFCStats id
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NamedFight:
    """A `fights` row with its two fighters' names, as CFL stores them."""

    id: int
    event_id: int
    fighter_names: tuple[str, str]


class LinkRefused(SourceError):
    """A card could not be linked completely. Nothing is written."""


def link_by_pair(card: SourceCard, fights: list[NamedFight], event_id: int) -> list[tuple[int, int]]:
    """[(fight_id, walkout)] for every bout, or LinkRefused.

    The UFCStats path links by UFCStats fight id and never by name, because
    eight pairs of fighters in the database share a name. A source with no
    UFCStats id can only link by name, so the rule here is the narrowest one
    that is still safe:

      * only fights already on THIS event are candidates;
      * BOTH corners must match (spacing, case, accents and punctuation folded,
        nothing else — no nicknames, no surname-only, no fuzzy distance);
      * exactly one fight row may match, or the card is refused;
      * every bout on the card must link, or the card is refused — one
        unlinked bout renumbers every bout after it.

    A fighter sharing a name with another fighter on the same card would make
    the pair ambiguous; that refuses rather than guesses.
    """
    on_event = [f for f in fights if f.event_id == event_id]
    out, problems, used = [], [], set()
    for bout in card.bouts:
        matches = [f for f in on_event if same_pair(f.fighter_names, bout.fighter_names)]
        if len(matches) != 1:
            problems.append(f"{bout.matchup!r}: {len(matches)} fight rows on event "
                            f"{event_id} match both corners"
                            + (f" ({[m.id for m in matches]})" if matches else ""))
            continue
        if matches[0].id in used:
            problems.append(f"{bout.matchup!r}: fight {matches[0].id} already linked")
            continue
        used.add(matches[0].id)
        out.append((matches[0].id, bout.walkout))
    if problems:
        raise LinkRefused(f"refusing a partial running order for event {event_id} from "
                          f"{card.source}: " + "; ".join(problems))
    return out


# ---------------------------------------------------------------------------
# Fixture serialisation (how the real samples are stored and checked)
# ---------------------------------------------------------------------------
def espn_fixture_text(fixture: dict) -> str:
    """One competition per line, so a fixture is small and reviewable in a diff."""
    import json

    def dump(o):
        return json.dumps(o, ensure_ascii=False, separators=(",", ":"))

    events = fixture.get("events", [])
    lines = ['{"leagues":' + dump(fixture.get("leagues", [])) + ',"events":[']
    for i, e in enumerate(events):
        head = {k: v for k, v in e.items() if k != "competitions"}
        lines.append(dump(head)[:-1] + ',"competitions":[')
        comps = e.get("competitions", [])
        for j, c in enumerate(comps):
            lines.append(dump(c) + ("," if j < len(comps) - 1 else ""))
        lines.append("]}" + ("," if i < len(events) - 1 else ""))
    lines.append("]}")
    return "\n".join(lines) + "\n"


def fixture_canonical_sha(name: str, text: str) -> str:
    """sha256 that ignores layout: canonical JSON for .json, line-normalised text otherwise.

    The real samples were recovered from a job log, where layout (trailing
    spaces, line endings) is not reliable but content is. This hash pins the
    content.
    """
    import hashlib
    import json
    if name.endswith(".json"):
        canon = json.dumps(json.loads(text), ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    else:
        canon = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
