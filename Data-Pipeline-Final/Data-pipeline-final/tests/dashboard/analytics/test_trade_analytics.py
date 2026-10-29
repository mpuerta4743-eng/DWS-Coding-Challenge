from pathlib import Path
import tempfile
import unittest

import pandas as pd

from trade_analytics import load_trades, resolve_source, summarize


class TradeAnalyticsTests(unittest.TestCase):
    def test_flagged_and_missing_values_stay_in_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trades.parquet"
            rows = pd.DataFrame({
                "INT_TRADE_ID": [1, 2, 3], "STRING_TRADER_ID": ["t1"] * 3,
                "STRING_INSTRUMENT": ["ABC"] * 3, "STRING_ISIN": ["ISIN"] * 3,
                "INT_QUANTITY": [2, 3, 4], "STRING_SIDE": ["BUY", "SELL", "BUY"],
                "TIMESTAMP_TRADE_DATE": ["2025-01-15T09:00:00Z"] * 3,
                "FLOAT_TRADE_VALUE_USD": [-20, None, 30],
                "BOOLEAN_IS_QUALITY_VALID": [True, False, True],
                "STRING_QUALITY_FLAGS": ["", "missing_fx", ""],
                "STRING_STRATEGY": ["s1"] * 3, "STRING_ACCOUNT": ["a1"] * 3,
                "STRING_CURRENCY": ["USD"] * 3, "STRING_TRADE_TYPE": ["Normal"] * 3,
            })
            rows.to_parquet(path)
            summary = summarize(load_trades(path), ["STRING_INSTRUMENT"]).iloc[0]
            self.assertEqual(summary.Trades, 3)
            self.assertEqual(summary.Gross_USD, 50)
            self.assertEqual(summary.Missing_USD, 1)
            self.assertEqual(summary.Flagged, 1)
            rows["FLOAT_TRADE_VALUE_USD"] = None
            rows.to_parquet(path)
            self.assertTrue(pd.isna(summarize(load_trades(path), ["STRING_INSTRUMENT"]).iloc[0].Gross_USD))

    def test_silver_source_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            silver = root / "data/1_silver/trades_enriched.parquet"
            silver.parent.mkdir(parents=True)
            silver.touch()
            self.assertEqual(resolve_source(root), silver)
            self.assertEqual(resolve_source(root, str(silver)), silver.resolve())


if __name__ == "__main__":
    unittest.main()

