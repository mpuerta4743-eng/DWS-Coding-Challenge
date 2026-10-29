import tempfile
from pathlib import Path
import unittest

import pandas as pd

from data_pipeline.quality_checks import check_enriched_parquet, quality_passed


class QualityCheckTests(unittest.TestCase):
    def test_bad_persisted_rows_are_counted_without_modification(self):
        frame = pd.DataFrame({
            "INT_TRADE_ID": pd.Series([1, 1, 2, None], dtype="Int64"),
            "BOOLEAN_HAS_SECURITY": pd.Series([True, False, None, False], dtype="boolean"),
            "BOOLEAN_IS_QUALITY_VALID": pd.Series([True, False, False, False], dtype="boolean"),
            "FLOAT_TRADE_VALUE_USD": [10.0, None, float("inf"), 20.0],
            "STRING_QUALITY_FLAGS": pd.Series(["", "SECURITY_NOT_FOUND", "BAD", "BAD"], dtype="string"),
            "STRING_SIDE": pd.Series(["BUY", "SELL", "buy", None], dtype="string"),
        })
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.parquet"
            frame.to_parquet(path, index=False)
            original = path.read_bytes()
            report = check_enriched_parquet(path)
            self.assertEqual(path.read_bytes(), original)
        self.assertEqual(report, {"total_trades": 4, "trades_without_security": 2,
            "null_security_flags": 1, "duplicate_trade_id_rows": 2, "duplicate_trade_ids": 1,
            "null_trade_ids": 1, "invalid_side_rows": 2, "invalid_quality_rows": 3,
            "invalid_usd_value_rows": 2})
        self.assertFalse(quality_passed(report))

    def test_valid_persisted_rows_pass(self):
        frame = pd.DataFrame({
            "INT_TRADE_ID": [1, 2], "BOOLEAN_HAS_SECURITY": [True, True],
            "BOOLEAN_IS_QUALITY_VALID": [True, True], "FLOAT_TRADE_VALUE_USD": [10.0, 20.0],
            "STRING_QUALITY_FLAGS": ["", ""], "STRING_SIDE": ["BUY", "SELL"],
        })
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "good.parquet"
            frame.to_parquet(path, index=False)
            self.assertTrue(quality_passed(check_enriched_parquet(path)))

    def test_missing_columns_and_non_boolean_flags_are_rejected(self):
        for frame in [pd.DataFrame({"id": [1]}), pd.DataFrame({
            "INT_TRADE_ID": [1], "BOOLEAN_HAS_SECURITY": ["FALSE"],
            "BOOLEAN_IS_QUALITY_VALID": [True], "FLOAT_TRADE_VALUE_USD": [10.0],
            "STRING_QUALITY_FLAGS": [""], "STRING_SIDE": ["BUY"],
        })]:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "invalid.parquet"
                frame.to_parquet(path, index=False)
                with self.assertRaises((ValueError, TypeError)):
                    check_enriched_parquet(path)
