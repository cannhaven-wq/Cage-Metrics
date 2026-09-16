"""The catalogue of data-integrity checks.

Each check is a counting query and three pieces of prose: what it counts, why
that matters to somebody who does not read SQL, and who decides what to do.

Classification — the only three answers
---------------------------------------
``AUTO``    Safe to fix automatically. Reversible, no cost, and it cannot change
            what any frozen definition means. In practice this is limited to
            flagging and read-path fixes; it never edits an observation.
``REVIEW``  Needs methodological review. Fixing it would change what a number
            means, which sample a statistic runs on, or how a record is read.
``L3``      The owner decides. Identity, money, publication, or anything where
            the honest options disagree about what actually happened.

Nothing here is classified ``AUTO`` if the fix would delete a historical
observation or write a fact we never observed. That is the line, and it is the
reason several of these sit at ``REVIEW`` despite having an obvious-looking fix.

Baselines
---------
Every check carries the count measured on 2026-09-16. A later run that comes in
higher means something new broke; one that comes in lower means something was
cleaned up. Both are worth a look, and neither is inferred — `run_audit.py`
prints the delta and says which.
"""
from __future__ import annotations

from dataclasses import dataclass

AUTO = "safe to fix automatically"
REVIEW = "needs methodological review"
L3 = "L3 / owner decision"
NOTE = "not a defect — recorded so it is not rediscovered as one"


@dataclass(frozen=True)
class Check:
    key: str
    title: str
    sql: str            # must return exactly one row, one integer column `n`
    why: str            # plain English, no jargon
    classification: str
    baseline: int       # measured 2026-09-16
    unit: str = "rows"


CHECKS: tuple[Check, ...] = (
    # ---------------------------------------------------------------- identity
    Check(
        key="odds_fighter_not_in_fight",
        title="Odds rows naming a fighter who is not in that fight",
        sql="""
            select count(*) n from fight_odds o join fights f on f.id = o.fight_id
            where o.fighter_id not in (coalesce(f.fighter_a_id,-1), coalesce(f.fighter_b_id,-2))
        """,
        why="A price is stored against a fighter who never fought in that bout. "
            "Whoever reads it gets a number for the wrong contest. It happens "
            "when a fight row's participants are replaced after the odds were "
            "captured.",
        classification=L3,
        baseline=104,
    ),
    Check(
        key="preds_fighter_not_in_fight",
        title="Predictions naming a fighter who is not in that fight",
        sql="""
            select count(*) n from model_predictions p join fights f on f.id = p.fight_id
            where p.fighter_id not in (coalesce(f.fighter_a_id,-1), coalesce(f.fighter_b_id,-2))
        """,
        why="We published a pick on one matchup and the fight row now holds a "
            "different one. Grading it scores our call on a fight we never "
            "called.",
        classification=L3,
        baseline=8,
    ),
    Check(
        key="odds_side_contradicts_fighter",
        title="Odds rows whose side letter contradicts their fighter",
        sql="""
            select count(*) n from fight_odds o join fights f on f.id = o.fight_id
            where (o.side = 'A' and o.fighter_id = f.fighter_b_id)
               or (o.side = 'B' and o.fighter_id = f.fighter_a_id)
        """,
        why="The row says side A and names the fighter in corner B. Every odds "
            "view reads the letter, not the name, so those fights come out with "
            "the two corners' prices swapped.",
        classification=REVIEW,
        baseline=1578,
    ),
    Check(
        key="duplicate_bout_same_event",
        title="The same matchup stored twice on one card",
        sql="""
            select count(*) n from (
              select event_id from fights
              where fighter_a_id is not null and fighter_b_id is not null
              group by event_id, least(fighter_a_id, fighter_b_id), greatest(fighter_a_id, fighter_b_id)
              having count(*) > 1
            ) x
        """,
        why="One real fight appears as two rows, so anything that counts fights "
            "counts it twice. One pair is genuine — Sakuraba and Silveira really "
            "did fight twice at Ultimate Japan in 1997.",
        classification=REVIEW,
        baseline=4,
        unit="matchups",
    ),
    Check(
        key="fighter_twice_on_modern_card",
        title="A fighter booked twice on the same card, 2000 onwards",
        sql="""
            select count(*) n from (
              select s.event_id, s.fid from (
                select id, event_id, fighter_a_id fid from fights where fighter_a_id is not null
                union all
                select id, event_id, fighter_b_id from fights where fighter_b_id is not null
              ) s join events e on e.id = s.event_id
              where e.event_date >= date '2000-01-01'
              group by 1, 2 having count(*) > 1
            ) x
        """,
        why="Nobody fights twice on a modern card. When the database says they "
            "do, one of the two bookings is dead — usually an opponent change "
            "where the old row was never retired. Before 2000 the tournament "
            "format made it real, so those are excluded.",
        classification=REVIEW,
        baseline=31,
        unit="fighter-events",
    ),
    Check(
        key="settled_card_fight_with_no_result",
        title="Fights on a finished card that never got a result",
        sql="""
            select count(*) n from fights f join events e on e.id = f.event_id
            where coalesce(e.is_upcoming, false) = false and e.event_date < current_date
              and f.winner_id is null and f.method is null
        """,
        why="The card is over and this bout has no winner and no method, which "
            "means it never happened — the booking fell off and the row stayed. "
            "It still shows up in any count of fights on that card.",
        classification=REVIEW,
        baseline=36,
    ),
    Check(
        key="multi_main_event",
        title="Cards claiming more than one main event",
        sql="""
            select count(*) n from (
              select event_id from fights where is_main_event group by 1 having count(*) > 1
            ) x
        """,
        why="A card has one main event. Two means a retired booking is still "
            "flying the flag, and anything that picks 'the main event' picks "
            "whichever it happens to read first.",
        classification=REVIEW,
        baseline=3,
        unit="events",
    ),

    # ----------------------------------------------------------- timestamps
    Check(
        key="odds_epoch_capture_time",
        title="Odds rows stamped 1 January 1970",
        sql="""
            select count(*) n from fight_odds where captured_at < timestamptz '1990-01-01'
        """,
        why="These prices carry a placeholder time, not a real one. They are the "
            "whole historical odds archive and the prices themselves are fine — "
            "but nothing can say when we saw them, so they can never establish "
            "what a price was shortly before a fight.",
        classification=REVIEW,
        baseline=30724,
    ),
    Check(
        key="odds_captured_in_the_future",
        title="Odds rows captured after now",
        sql="select count(*) n from fight_odds where captured_at > now()",
        why="A price we have not seen yet, stamped later than the moment the "
            "check ran. It is always a broken clock somewhere, and it puts a "
            "quote on the wrong side of any before-the-fight cutoff.",
        classification=AUTO,
        baseline=0,
    ),
    Check(
        key="fights_with_a_bell_time",
        title="Fights with a confirmed start time",
        sql="select count(*) n from fights where bell_at is not null",
        why="Zero. Nothing in the database records when any fight actually "
            "started, which is why running order and bout completions matter. "
            "This check is watching for the number to go UP.",
        classification=NOTE,
        baseline=0,
        unit="fights",
    ),

    # ------------------------------------------------------------- prices
    Check(
        key="odds_resolved_market_as_closer",
        title="A settled market price flagged as a closing price",
        sql="""
            select count(*) n from fight_odds o
            join fights f on f.id = o.fight_id join events e on e.id = f.event_id
            where o.is_closer and abs(o.american_odds) >= 10000
              and o.captured_at >= (e.event_date + 1)::timestamptz
        """,
        why="A price of 99.95% taken after the card is a market that has already "
            "paid out, not a price anyone could have bet. Counted as a closing "
            "price it would make our forecasting look perfect.",
        classification=L3,
        baseline=2,
    ),
    Check(
        key="odds_extreme_price",
        title="Prices past 100-to-1 either way",
        sql="select count(*) n from fight_odds where abs(american_odds) >= 10000",
        why="Real sportsbooks do not price a fight at 100-to-1. These come from "
            "prediction markets near or after settlement, where the number stops "
            "being a forecast.",
        classification=REVIEW,
        baseline=61,
    ),
    Check(
        key="odds_implied_prob_disagrees",
        title="Stored probability that does not match its own price",
        sql="""
            select count(*) n from fight_odds where implied_prob is not null and abs(
              implied_prob - case when american_odds > 0 then 100.0 / (american_odds + 100)
                                  else (-american_odds)::numeric / ((-american_odds) + 100) end
            ) > 0.005
        """,
        why="Each row stores a price and the probability that price implies. If "
            "they disagree, one of them is wrong and no reader can tell which.",
        classification=AUTO,
        baseline=0,
    ),
    Check(
        key="odds_duplicate_market_identity",
        title="Two quotes for the same book, fight, side and instant",
        sql="""
            select count(*) n from (
              select fight_id, book_id, side, captured_at from fight_odds
              group by 1, 2, 3, 4 having count(*) > 1
            ) x
        """,
        why="One book cannot have two prices for the same side at the same "
            "moment. Duplicates would double-weight that book in any average.",
        classification=AUTO,
        baseline=0,
        unit="quote identities",
    ),
    Check(
        key="odds_multiple_closers",
        title="More than one closing price per book and side",
        sql="""
            select count(*) n from (
              select fight_id, book_id, side from fight_odds where is_closer
              group by 1, 2, 3 having count(*) > 1
            ) x
        """,
        why="There is one last price. Two flagged as last means whichever is "
            "read first wins, which is a coin flip dressed as a record.",
        classification=AUTO,
        baseline=0,
        unit="book-sides",
    ),

    # ------------------------------------------------------- referential
    Check(
        key="orphan_rows",
        title="Rows pointing at a fight, fighter, event or book that is gone",
        sql="""
            select (
              (select count(*) from fights f left join events e on e.id = f.event_id where f.event_id is not null and e.id is null)
            + (select count(*) from fight_odds o left join fights f on f.id = o.fight_id where f.id is null)
            + (select count(*) from fight_odds o left join odds_books b on b.id = o.book_id where b.id is null)
            + (select count(*) from model_predictions p left join fights f on f.id = p.fight_id where f.id is null)
            + (select count(*) from model_picks p left join fights f on f.id = p.fight_id where f.id is null)
            + (select count(*) from model_edges p left join fights f on f.id = p.fight_id where f.id is null)
            ) n
        """,
        why="A row whose parent no longer exists. None today, and that is worth "
            "keeping true.",
        classification=AUTO,
        baseline=0,
    ),
    Check(
        key="prediction_event_date_mismatch",
        title="Predictions dated differently from their event",
        sql="""
            select (
              (select count(*) from model_picks p join fights f on f.id = p.fight_id join events e on e.id = f.event_id where p.event_date <> e.event_date)
            + (select count(*) from model_predictions p join fights f on f.id = p.fight_id join events e on e.id = f.event_id where p.event_date <> e.event_date)
            + (select count(*) from model_edges p join fights f on f.id = p.fight_id join events e on e.id = f.event_id where p.event_date <> e.event_date)
            ) n
        """,
        why="Every prediction carries the card's date so it can be cut "
            "out-of-sample. A copy that drifts from the event's own date puts a "
            "fight in the wrong window.",
        classification=AUTO,
        baseline=0,
    ),
    Check(
        key="stale_upcoming_events",
        title="Cards still marked upcoming after their date",
        sql="select count(*) n from events where is_upcoming and event_date < current_date",
        why="A finished card still advertised as upcoming shows stale fights on "
            "the site and keeps odds capture pointed at a card that is over.",
        classification=AUTO,
        baseline=0,
        unit="events",
    ),
    Check(
        key="duplicate_fighter_names",
        title="Two fighter records sharing one name",
        sql="""
            select count(*) n from (
              select lower(btrim(name)) from fighters group by 1 having count(*) > 1
            ) x
        """,
        why="Namesakes are real — there are two Bruno Silvas. It is recorded here "
            "because it is the reason nothing in this codebase is allowed to "
            "match a fighter by name.",
        classification=NOTE,
        baseline=8,
        unit="names",
    ),

    # -------------------------------------------------------- era artifacts
    Check(
        key="impossible_round_clock_modern",
        title="Rounds longer than five minutes, 2001 onwards",
        sql="""
            select count(*) n from fights f join events e on e.id = f.event_id
            where e.event_date >= date '2001-01-01'
              and f.end_time ~ '^[0-9]{1,2}:[0-9]{2}$'
              and (split_part(f.end_time, ':', 1)::int * 60 + split_part(f.end_time, ':', 2)::int) > 300
        """,
        why="A modern round is five minutes. A longer one is a typo. The 48 that "
            "exist are all pre-2001, when rounds genuinely ran long, so the check "
            "starts at 2001 — the old fights are history, not errors.",
        classification=AUTO,
        baseline=0,
        unit="fights",
    ),
    Check(
        key="end_round_past_scheduled_modern",
        title="Fights ending in a round they were not scheduled to reach, 2001 onwards",
        sql="""
            select count(*) n from fights f join events e on e.id = f.event_id
            where e.event_date >= date '2001-01-01'
              and f.end_round is not null and f.scheduled_rounds is not null
              and f.end_round > f.scheduled_rounds
        """,
        why="A three-round fight cannot end in round four. All 29 that exist are "
            "pre-2001 tournament bouts, where the scheduled length was recorded "
            "differently.",
        classification=AUTO,
        baseline=0,
        unit="fights",
    ),
)


def by_key(key: str) -> Check:
    for c in CHECKS:
        if c.key == key:
            return c
    raise KeyError(key)
