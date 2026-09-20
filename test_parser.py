"""Offline regression tests: dates, missing readings and validation."""
import unittest
from datetime import date
from kyuden.parsing import parse_daily, parse_hourly

def chart(labels, readings):
    return {"shiyoKikan": ["x", *labels], "columns": [["kWh", *readings]]}

class ParserTests(unittest.TestCase):
    def test_cross_year(self):
        rows = parse_daily(chart(["12/31", "1/1"], [1, 2]), date(2026, 1, 2))
        self.assertEqual([r["date"] for r in rows], [date(2025, 12, 31), date(2026, 1, 1)])

    def test_prior_month_and_missing(self):
        rows = parse_daily(chart(["8/31", "9/1", "9/2"], [0, 2, None]), date(2026, 9, 2))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], date(2026, 8, 31))
        self.assertEqual(rows[0]["usage_kwh"], 0)

    def test_leap_day(self):
        self.assertEqual(parse_daily(chart(["2/29"], [1]), date(2024, 3, 1))[0]["date"], date(2024, 2, 29))

    def test_invalid_daily_data(self):
        cases = [
            chart(["9/1"], [1, 2]), chart(["9/1", "9/1"], [1, 2]),
            chart(["1/1"], [1]), chart(["2/30"], [1]),
            chart(["9/1"], [-1]), chart(["9/1"], [float("nan")]),
            chart(["9/1"], [True]),
        ]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_daily(data, date(2026, 9, 2))

    def test_hourly_null_preserves_hour(self):
        rows = parse_hourly(chart([], [0, None, 2]), date(2026, 9, 2))
        self.assertEqual([r["hour"] for r in rows], [0, 2])

    def test_hourly_rejects_extra_slots(self):
        with self.assertRaises(ValueError):
            parse_hourly(chart([], [1] * 25))

if __name__ == "__main__":
    unittest.main()
