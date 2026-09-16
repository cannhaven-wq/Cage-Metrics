"""Tripwire: the CLV protocol's gates must hold, and its two copies must agree.

    python -m unittest tests/test_clv_protocol.py -v

CLV is the number that separates a real model from a good-looking replay of
history, which makes it the number most worth publishing early and least safe to
publish early. Reed's rule is that raw quotes capture immediately but no CLV
figure reaches a surface until the protocol is frozen.

That rule is only worth anything if something enforces it, so:

  * while the protocol is not frozen, the publication gate must be shut, and the
    protocol must not claim a freeze it has not had;
  * capture must stay open — a protocol that accidentally blocks collection
    loses data that cannot be recovered;
  * `results_computed_before_freeze` must be false, the same discipline as
    `motivated_by_observed_results` in the research registry;
  * the markdown and the JSON mirror must not drift, because the drifting copy
    would be the one nobody reads.

What this cannot check is whether a human looked at the data and then chose a
definition. That is what the §9 disclosure is for.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
CLV = REPO / "research" / "clv"
PROTOCOL_MD = CLV / "CLV_MEASUREMENT_PROTOCOL.md"
PROTOCOL_JSON = CLV / "protocol.json"

STATUSES = ("draft", "under-review", "frozen")
LEVELS = {"L0", "L1", "L2", "L3"}

# | Q-01 | what "closing line" means | L2 |   (level may be bolded)
Q_ROW = re.compile(r"^\|\s*(Q-\d{2})\s*\|\s*(.+?)\s*\|\s*\*{0,2}(L[0-3])\*{0,2}\s*\|\s*$")
# ### R-01 — Raw capture is immediate...
R_HEAD = re.compile(r"^###\s+(R-\d{2})\s")


def doc() -> dict:
    return json.loads(PROTOCOL_JSON.read_text(encoding="utf-8"))


def markdown() -> str:
    return PROTOCOL_MD.read_text(encoding="utf-8")


def md_questions() -> dict[str, str]:
    """{Q-id: level} from the §8 summary table."""
    return {m.group(1): m.group(3)
            for line in markdown().splitlines() if (m := Q_ROW.match(line))}


class TestFilesExist(unittest.TestCase):
    def test_protocol_markdown_exists(self):
        self.assertTrue(PROTOCOL_MD.is_file(), f"missing {PROTOCOL_MD}")

    def test_protocol_json_exists_and_parses(self):
        self.assertTrue(PROTOCOL_JSON.is_file(), f"missing {PROTOCOL_JSON}")
        self.assertEqual(doc()["protocol_id"], "CLV-001")


class TestGates(unittest.TestCase):
    """The load-bearing checks."""

    def test_status_is_known(self):
        self.assertIn(doc()["status"], STATUSES)

    def test_publication_is_blocked_until_frozen(self):
        d = doc()
        if d["status"] == "frozen":
            self.skipTest("protocol is frozen; publication gate legitimately open")
        self.assertIs(
            d["publication_gate"]["publication_allowed"], False,
            "\n\nThe CLV protocol is not frozen but its publication gate is open.\n"
            "No CLV figure may reach a page, post, email or digest until the "
            "protocol is frozen — see research/clv/CLV_MEASUREMENT_PROTOCOL.md "
            "R-10 and coordination/DECISIONS.md D-003.\n",
        )

    def test_capture_is_never_blocked(self):
        """The one gate that must stay open. A quote not captured today cannot be
        captured later, and several definitions in §3 depend on fields that can
        only be collected prospectively."""
        self.assertIs(
            doc()["capture_gate"]["capture_allowed"], True,
            "raw quote capture must remain allowed — unlike publication, "
            "collection cannot be caught up afterwards",
        )

    def test_an_unfrozen_protocol_claims_no_freeze(self):
        d = doc()
        if d["status"] == "frozen":
            self.skipTest("protocol is frozen")
        for field in ("frozen_at", "frozen_by", "protocol_sha256"):
            with self.subTest(field=field):
                self.assertIsNone(
                    d[field],
                    f"status is {d['status']!r} but {field} is set — a draft that "
                    f"records a freeze reads as binding when it is not",
                )

    def test_a_frozen_protocol_records_its_freeze_and_matches_disk(self):
        d = doc()
        if d["status"] != "frozen":
            self.skipTest("protocol is not frozen yet")
        self.assertIsNotNone(d["frozen_at"])
        self.assertIsNotNone(d["frozen_by"])
        actual = hashlib.sha256(PROTOCOL_MD.read_bytes()).hexdigest()
        self.assertEqual(
            d["protocol_sha256"], actual,
            "\n\nThe frozen CLV protocol no longer matches its recorded hash.\n"
            "Do not update the hash to make this pass. Either a dated amendment "
            "or a new protocol version — see §5.\n",
        )

    def test_no_results_were_computed_before_freeze(self):
        """Mirrors motivated_by_observed_results in the research registry: recorded
        false, and required to actually be false."""
        self.assertIs(doc()["results_computed_before_freeze"], False)

    def test_markdown_status_banner_agrees_with_json(self):
        d = doc()
        if d["status"] != "draft":
            self.skipTest("banner check is written for the draft state")
        self.assertIn(
            "Status: DRAFT", markdown(),
            "protocol.json says draft but the markdown does not say so at the top, "
            "where a reader would see it",
        )


class TestOpenQuestions(unittest.TestCase):
    def test_there_are_open_questions_to_check(self):
        self.assertGreater(len(doc()["open_questions"]), 0)

    def test_every_question_is_well_formed(self):
        for q in doc()["open_questions"]:
            with self.subTest(question=q.get("id")):
                self.assertRegex(q["id"], r"^Q-\d{2}$")
                self.assertIn(q["level"], LEVELS)
                self.assertTrue(q["question"].strip())
                self.assertGreaterEqual(
                    len(q.get("options") or []), 2,
                    "an 'open question' with fewer than two options is a decided "
                    "rule wearing the wrong label",
                )
                self.assertTrue(q.get("recommendation", "").strip())

    def test_no_question_was_chosen_by_historical_comparison(self):
        """Reed: do not calculate historical 'best' definitions to choose among
        alternatives. Recorded per question, and required to be false."""
        for q in doc()["open_questions"]:
            with self.subTest(question=q["id"]):
                self.assertIs(
                    q["chosen_by_historical_comparison"], False,
                    f"{q['id']} records being chosen by historical comparison. "
                    f"A definition picked because it scored better is not a "
                    f"preregistered definition.",
                )

    def test_question_ids_are_unique(self):
        ids = [q["id"] for q in doc()["open_questions"]]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate question ids in {ids}")

    def test_json_and_markdown_list_the_same_questions(self):
        """The registry-agreement pattern: two hand-maintained copies drift, and
        the drifting one is always the copy nobody reads."""
        js = {q["id"]: q["level"] for q in doc()["open_questions"]}
        md = md_questions()
        self.assertEqual(
            set(js), set(md),
            f"§8 summary table and protocol.json disagree on which questions "
            f"exist: only in JSON {sorted(set(js) - set(md))}, only in markdown "
            f"{sorted(set(md) - set(js))}",
        )
        for qid in sorted(js):
            with self.subTest(question=qid):
                self.assertEqual(
                    js[qid], md[qid],
                    f"{qid} is {js[qid]} in protocol.json but {md[qid]} in the "
                    f"markdown summary table",
                )

    def test_an_l3_question_says_why(self):
        """L3 is escalation to Reed. If a question claims it without a reason, it
        is either mislabelled or padding the owner's queue."""
        for q in doc()["open_questions"]:
            if q["level"] != "L3":
                continue
            with self.subTest(question=q["id"]):
                self.assertTrue(
                    (q.get("why_l3") or "").strip(),
                    f"{q['id']} is L3 but records no why_l3",
                )


class TestDecidedRules(unittest.TestCase):
    def test_every_decided_rule_is_well_formed(self):
        for r in doc()["decided_rules"]:
            with self.subTest(rule=r.get("id")):
                self.assertRegex(r["id"], r"^R-\d{2}$")
                self.assertTrue(r["title"].strip())
                self.assertTrue(
                    r.get("basis", "").strip(),
                    "a decided rule with no basis is an undocumented choice",
                )

    def test_rule_ids_are_unique(self):
        ids = [r["id"] for r in doc()["decided_rules"]]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate rule ids in {ids}")

    def test_every_json_rule_appears_in_the_markdown(self):
        body = markdown()
        headed = {m.group(1) for line in body.splitlines() if (m := R_HEAD.match(line))}
        for r in doc()["decided_rules"]:
            with self.subTest(rule=r["id"]):
                self.assertIn(
                    r["id"], headed,
                    f"{r['id']} is in protocol.json but has no §2 section in the "
                    f"markdown",
                )

    def test_the_publication_and_firewall_rules_are_present(self):
        """These two are the ones Reed's instruction rests on. Losing either to a
        tidy-up would remove the gate without removing the appearance of one."""
        ids = {r["id"] for r in doc()["decided_rules"]}
        for rid in ("R-09", "R-10"):
            with self.subTest(rule=rid):
                self.assertIn(rid, ids)


class TestCaptureRequirements(unittest.TestCase):
    def test_backfill_impossible_requirements_are_listed(self):
        """§4's whole point: an omission here is the only error in the document
        that cannot be fixed later."""
        reqs = doc()["capture_requirements_that_cannot_be_backfilled"]
        self.assertGreater(len(reqs), 0)
        joined = " ".join(reqs).lower()
        self.assertIn(
            "both sides", joined,
            "two-sided capture at the publish instant is what makes the de-vigged "
            "variant in Q-05 possible at all; it cannot be backfilled and must "
            "stay on this list",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
