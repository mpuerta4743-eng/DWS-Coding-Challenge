from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

import pandas as pd

from importlib import import_module

pipeline = import_module("data_pipeline.data_pipeline")
apply_semantics = pipeline.apply_semantics
semanticize_bronze = pipeline.semanticize_bronze
transform_silver = pipeline.transform_silver
enrich_silver = pipeline.enrich_silver
read_bronze = pipeline.read_bronze
run_bronze_to_silver = pipeline.run_bronze_to_silver
from data_pipeline.schemas import DatasetSchema


from tests.fixtures import BronzeFixtureMixin


class SilverPublicationTests(BronzeFixtureMixin, unittest.TestCase):
    def test_silver_writes_typed_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bronze, silver = Path(temp) / "bronze", Path(temp) / "silver"
            bronze.mkdir()
            for name, frame in (("trades", self.trades), ("securities", self.securities), ("currencies", self.currencies)):
                if name == "trades":
                    frame.drop(columns=["timestamp_file_processed"]).to_xml(
                        bronze / "trades.xml", root_name="trades", row_name="trade", index=False,
                        parser="etree",
                    )
                else:
                    frame.to_csv(bronze / f"{name}.csv", index=False)
            original = (bronze / "trades.xml").read_bytes()
            raw_frames = read_bronze(bronze)
            self.assertIn("tradeDate", raw_frames[0])
            self.assertNotIn("trade_value", raw_frames[0])
            self.assertFalse(silver.exists())
            expected = run_bronze_to_silver(bronze, silver)
            self.assertEqual((bronze / "trades.xml").read_bytes(), original)
            self.assertTrue(expected["TIMESTAMP_FILE_PROCESSED"].notna().all())
            self.assertIn("INT_TRADE_ID", expected)
            self.assertEqual(str(expected["INT_QUANTITY"].dtype), "Int64")
            self.assertNotIn("FLOAT_QUANTITY", expected)
            self.assertIn("STRING_ISIN", expected)
            self.assertIn("FLOAT_TRADE_VALUE_USD", expected)
            self.assertNotIn("TIMESTAMP_VALID_FROM", expected)
            self.assertNotIn("TIMESTAMP_VALID_TO", expected)
            self.assertIn("BOOLEAN_IS_QUALITY_VALID", expected)
            self.assertNotIn("has_security", expected)
            self.assertEqual(str(expected["BOOLEAN_HAS_SECURITY"].dtype), "boolean")
            pd.testing.assert_frame_equal(pd.read_parquet(silver / "trades_enriched.parquet"), expected)
            self.assertEqual([p.name for p in silver.iterdir()], ["trades_enriched.parquet"])

