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


class SilverEnrichmentTests(BronzeFixtureMixin, unittest.TestCase):
    def test_security_join_retains_matched_unmatched_and_duplicate_trades(self):
        trades = pd.concat([self.trades] * 4, ignore_index=True)
        trades["isin"] = ["KNOWN", "UNKNOWN", "KNOWN", pd.NA]
        securities = pd.concat([self.securities] * 2, ignore_index=True)
        securities.loc[len(securities)] = [pd.NA, "EUR", "unused"]
        silver = enrich_silver(*transform_silver(trades, securities, self.currencies))
        self.assertEqual(len(silver), len(trades))
        self.assertEqual(silver["trade_id"].tolist(), [1, 1, 1, 1])
        self.assertEqual(silver["has_security"].tolist(), [True, False, True, False])
        self.assertEqual(str(silver["has_security"].dtype), "boolean")
        self.assertFalse(silver["has_security"].isna().any())
        self.assertEqual(silver.loc[1, "quality_flags"], "SECURITY_NOT_FOUND;DUPLICATE_TRADE_ID")
        self.assertEqual(silver.loc[3, "quality_flags"], "SECURITY_NOT_FOUND;DUPLICATE_TRADE_ID")


    def test_empty_security_table_retains_every_trade(self):
        silver = enrich_silver(*transform_silver(
            self.trades, self.securities.iloc[:0], self.currencies
        ))
        self.assertEqual(len(silver), len(self.trades))
        self.assertEqual(silver["has_security"].tolist(), [False])


    def test_security_match_does_not_depend_on_currency_or_rate(self):
        for currency in [pd.NA, "GBP"]:
            with self.subTest(currency=currency):
                securities = self.securities.copy()
                securities["currency"] = currency
                silver = enrich_silver(*transform_silver(self.trades, securities, self.currencies))
                self.assertEqual(len(silver), len(self.trades))
                self.assertEqual(silver["has_security"].tolist(), [True])
                self.assertTrue(silver["fx_rate_to_usd"].isna().all())
                expected = (
                    "CURRENCY_MISSING" if pd.isna(currency)
                    else "CURRENCY_RATE_NOT_VALID_FOR_TRADE"
                )
                self.assertEqual(silver.loc[0, "quality_flags"], expected)
                self.assertFalse(silver.loc[0, "is_quality_valid"])


    def test_invalid_values_dates_and_rates_are_flagged_without_dropping_trades(self):
        trades = pd.concat([self.trades] * 4, ignore_index=True)
        trades["tradeId"] = ["1", "2", "3", "4"]
        trades.loc[0, "price"] = "inf"
        trades.loc[1, "tradeDate"] = "not-a-date"
        currencies = pd.concat([self.currencies] * 2, ignore_index=True)
        currencies.loc[0, "fx_rate_to_usd"] = "0"
        currencies.loc[1, "valid_from"] = "2025-01-16T00:00:00Z"
        currencies.loc[1, "valid_to"] = "2025-01-17T00:00:00Z"

        silver = enrich_silver(*transform_silver(trades, self.securities, currencies))

        self.assertEqual(len(silver), 4)
        self.assertIn("INVALID_TRADE_VALUE", silver.loc[0, "quality_flags"])
        self.assertIn("INVALID_FX_RATE", silver.loc[0, "quality_flags"])
        self.assertEqual(silver.loc[1, "quality_flags"], "INVALID_TRADE_DATE")
        self.assertNotIn("CURRENCY_RATE_NOT_VALID_FOR_TRADE", silver.loc[1, "quality_flags"])
        self.assertTrue(silver.loc[[0, 1], "trade_value_usd"].isna().all())
        self.assertFalse(silver.loc[[0, 1], "is_quality_valid"].any())


    def test_negative_and_infinite_fx_rates_are_invalid(self):
        for rate in ["-1", "inf"]:
            with self.subTest(rate=rate):
                currencies = self.currencies.copy()
                currencies.loc[0, "fx_rate_to_usd"] = rate
                silver = enrich_silver(*transform_silver(
                    self.trades, self.securities, currencies
                ))
                self.assertEqual(silver.loc[0, "quality_flags"], "INVALID_FX_RATE")
                self.assertTrue(pd.isna(silver.loc[0, "trade_value_usd"]))


    def test_trade_id_and_side_checks_match_persisted_quality_rules(self):
        trades = pd.concat([self.trades] * 4, ignore_index=True)
        trades["tradeId"] = ["1", "1", None, "4"]
        trades["side"] = ["BUY", "SELL", "BUY", "HOLD"]

        silver = enrich_silver(*transform_silver(trades, self.securities, self.currencies))

        self.assertIn("DUPLICATE_TRADE_ID", silver.loc[0, "quality_flags"])
        self.assertIn("DUPLICATE_TRADE_ID", silver.loc[1, "quality_flags"])
        self.assertIn("TRADE_ID_MISSING", silver.loc[2, "quality_flags"])
        self.assertIn("INVALID_SIDE", silver.loc[3, "quality_flags"])
        self.assertFalse(silver["is_quality_valid"].any())


    def test_invalid_currency_rate_window_is_rejected(self) -> None:
        currencies = self.currencies.copy()
        currencies.loc[0, "valid_to"] = "2025-01-15T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "invalid validity windows"):
            enrich_silver(*transform_silver(self.trades, self.securities, currencies))


    def test_rate_is_selected_by_trade_timestamp(self) -> None:
        currencies = pd.concat([self.currencies, pd.DataFrame([{
            "currency": "EUR", "fx_rate_to_usd": "1.2",
            "valid_from": "2025-01-16T00:00:00Z", "valid_to": "2025-01-17T00:00:00Z",
        }])], ignore_index=True)
        silver = enrich_silver(*transform_silver(self.trades, self.securities, currencies))
        self.assertEqual(silver.iloc[0]["fx_rate_to_usd"], 1.1)
        self.assertNotIn("valid_from", silver)
        self.assertNotIn("valid_to", silver)

