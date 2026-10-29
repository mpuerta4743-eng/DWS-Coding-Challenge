from __future__ import annotations

import unittest

import pandas as pd

from importlib import import_module

pipeline = import_module("data_pipeline.data_pipeline")
apply_semantics = pipeline.apply_semantics
transform_silver = pipeline.transform_silver
enrich_silver = pipeline.enrich_silver
from data_pipeline.schemas import DatasetSchema


from tests.fixtures import BronzeFixtureMixin


class SilverTransformationTests(BronzeFixtureMixin, unittest.TestCase):
    def test_mixed_iso_timestamps_are_parsed_consistently_in_utc(self):
        trades = pd.concat([self.trades] * 3, ignore_index=True)
        trades["tradeDate"] = [
            "2025-01-15T09:00:00Z",
            "2025-01-15T10:00:00.123Z",
            "2025-01-15T12:00:00+02:00",
        ]
        transformed, _, _ = transform_silver(trades, self.securities, self.currencies)
        self.assertEqual(
            transformed["timestamp_trade_date"].tolist(),
            [
                pd.Timestamp("2025-01-15T09:00:00Z"),
                pd.Timestamp("2025-01-15T10:00:00.123Z"),
                pd.Timestamp("2025-01-15T10:00:00Z"),
            ],
        )


    def test_quantity_is_nullable_integer_and_rejects_fractional_units(self):
        trades = pd.concat([self.trades] * 2, ignore_index=True)
        trades["quantity"] = ["2", None]
        transformed, _, _ = transform_silver(trades, self.securities, self.currencies)
        self.assertEqual(str(transformed["quantity"].dtype), "Int64")
        self.assertEqual(transformed.loc[0, "quantity"], 2)
        self.assertTrue(pd.isna(transformed.loc[1, "quantity"]))
        trades.loc[0, "quantity"] = "2.5"
        with self.assertRaises((TypeError, ValueError)):
            transform_silver(trades, self.securities, self.currencies)


    def test_cleaning_normalizes_join_keys_and_values_without_changing_bronze(self):
        trades = self.trades.copy(deep=True)
        trades.loc[0, "isin"] = "  known  "
        trades.loc[0, "traderId"] = "  trader one  "
        trades.loc[0, "quantity"] = " 2 "
        trades.loc[0, "price"] = " 10.5 "
        trades.loc[0, "tradeDate"] = " 2025-01-15T09:00:00Z "
        securities = self.securities.copy(deep=True)
        securities.loc[0, "isin"] = " Known "
        securities.loc[0, "currency"] = " eur "
        currencies = self.currencies.copy(deep=True)
        currencies.loc[0, "currency"] = " Eur "
        originals = [frame.copy(deep=True) for frame in (trades, securities, currencies)]
        silver = enrich_silver(*transform_silver(trades, securities, currencies))
        self.assertEqual(silver.loc[0, "trader_id"], "TRADER ONE")
        self.assertEqual(silver.loc[0, "isin"], "KNOWN")
        self.assertEqual(silver.loc[0, "currency"], "EUR")
        self.assertTrue(silver.loc[0, "has_security"])
        self.assertAlmostEqual(silver.loc[0, "trade_value_usd"], 23.1)
        for before, after in zip(originals, (trades, securities, currencies)):
            pd.testing.assert_frame_equal(before, after)


    def test_text_cleaning_preserves_nulls_and_numeric_boolean_timestamp_types(self):
        frame = pd.DataFrame({"text": pd.Series([" a ", None], dtype="string"),
            "mixed": [" b ", 3], "count": pd.Series([2, None], dtype="Int64"),
            "flag": pd.Series([True, None], dtype="boolean"),
            "time": pd.to_datetime(["2025-01-15", None], utc=True)})
        result = pipeline.clean_text_values(frame)
        self.assertEqual(result.loc[0, "text"], "A")
        self.assertTrue(pd.isna(result.loc[1, "text"]))
        self.assertEqual(result["mixed"].tolist(), ["B", 3])
        pd.testing.assert_frame_equal(result[["count", "flag", "time"]], frame[["count", "flag", "time"]])
        self.assertEqual(frame.loc[0, "text"], " a ")


    def test_schema_arrays_must_have_same_length(self) -> None:
        schema = DatasetSchema(["a"], ["renamed_a", "b"], ["string"])
        with self.assertRaisesRegex(ValueError, "equal lengths"):
            apply_semantics(pd.DataFrame({"a": ["x"]}), schema)

