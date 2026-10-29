import tempfile
import unittest
from importlib import import_module
from pathlib import Path

import pandas as pd

from data_pipeline.silver_semantics import semanticize_silver


class SilverSemanticsTests(unittest.TestCase):
    def test_ambiguous_objects_and_wrong_prefixes_are_rejected(self):
        for frame in [pd.DataFrame({"value": [1, "x"]}),
                      pd.DataFrame({"value": [None]}),
                      pd.DataFrame({"STRING_COUNT": [1]})]:
            with self.subTest(columns=frame.columns.tolist()):
                with self.assertRaises((TypeError, ValueError)):
                    semanticize_silver(frame)

    def test_duplicate_names_and_prefix_collisions_are_rejected(self):
        for frame in [pd.DataFrame([[1, 2]], columns=["id", "id"]),
                      pd.DataFrame({"id": [1], "INT_ID": [2]})]:
            with self.assertRaises(ValueError):
                semanticize_silver(frame)

    def test_parquet_keeps_numeric_values(self):
        pipeline = import_module("data_pipeline.data_pipeline")
        frame = pd.DataFrame({
            "FLOAT_FX_RATE_TO_USD": pd.Series([1., 1.0292, 0.00635, None], dtype="Float64"),
            "FLOAT_PRICE": pd.Series([1.23456789] * 4, dtype="Float64"),
        })
        original = frame.copy(deep=True)
        with tempfile.TemporaryDirectory() as temp:
            pipeline.write_silver(frame, Path(temp))
            pd.testing.assert_frame_equal(pd.read_parquet(Path(temp) / "trades_enriched.parquet"), original)
            self.assertEqual([path.name for path in Path(temp).iterdir()], ["trades_enriched.parquet"])
        pd.testing.assert_frame_equal(frame, original)

    def test_uppercase_column_collisions_are_rejected(self):
        with self.assertRaises(ValueError):
            semanticize_silver(pd.DataFrame({"name": ["x"], "NAME": ["y"]}))

