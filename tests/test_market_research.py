"""Price-only market research (D-034, condition 5) never names a fight result.

Every file under research/market/ that is code or a query (.py, .sql, .js) is
scanned for result, method, round, finish-time and statistics columns and for
the results tables. A price-only study reads prices and booking fields only;
reading an outcome is not a convention it may break quietly.
"""
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
ROOT = REPO / "research" / "market"
FORBIDDEN = re.compile(
    r"\bwinner(_id)?\b|\bmethod(_detail)?\b|\bend_round\b|\bend_time\b|\bfight_rounds\b|"
    r"\b[ab]_(kd|sig_str_\w+|total_str_\w+|td_\w+|sub_attempts|rev|ctrl_seconds|head_landed|body_landed|"
    r"leg_landed|distance_landed|clinch_landed|ground_landed)\b|\bbonus\b|"
    r"v_pre_fight_graded|model_predictions|settle|\bwon\b|\boutcome\b|\bresult\b", re.I)


class PriceOnly(unittest.TestCase):
    def test_no_result_column_in_market_code(self):
        files = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in (".py", ".sql", ".js")]
        for p in files:
            for i, line in enumerate(p.read_text().splitlines(), 1):
                code = line.split("--", 1)[0] if p.suffix == ".sql" else line.split("#", 1)[0]
                m = FORBIDDEN.search(code)
                self.assertIsNone(m, f"{p.relative_to(REPO)}:{i} names '{m and m.group(0)}' outside a comment")

    def test_the_pattern_catches_what_it_should(self):
        for bad in ("f.winner_id", "a_sig_str_landed", "method", "join fight_rounds", "end_round"):
            self.assertRegex(bad, FORBIDDEN)
        for ok in ("american_odds", "retrieved_at", "fighter_a_id", "event_date", "market_status"):
            self.assertNotRegex(ok, FORBIDDEN)


if __name__ == "__main__":
    unittest.main()
