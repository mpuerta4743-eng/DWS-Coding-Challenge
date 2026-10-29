from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from importlib import import_module

fx_api = import_module('data_pipeline.fx_api')
FRANKFURTER_RATES_URL = fx_api.FRANKFURTER_RATES_URL
refresh_currency_table = fx_api.refresh_currency_table


class FxIngestionTests(unittest.TestCase):
    @staticmethod
    def write_securities(root: Path, currencies: list[str]) -> Path:
        path = root / "securities.csv"
        pd.DataFrame({
            "isin": [f"ISIN{index}" for index in range(len(currencies))],
            "currency": currencies,
        }).to_csv(path, index=False)
        return path

    @patch.object(fx_api.httpx, "get")
    def test_default_covers_trade_timestamps_and_enriches_usd_values(self, mock_get):
        from importlib import import_module
        pipeline = import_module("data_pipeline.data_pipeline")
        mock_get.return_value.json.return_value = [
            {"date": "2025-01-14", "rate": "1.10"},
            {"date": "2025-01-16", "rate": "1.20"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trades_file = root / "trades.xml"
            trades_file.write_text("<trades><trade><tradeDate>2025-01-16T23:59:59Z</tradeDate></trade>"
                                   "<trade><tradeDate>2025-01-15T01:00:00+02:00</tradeDate></trade></trades>")
            table = root / "currencies.csv"
            table.write_text("currency\nEUR\n")
            securities_file = self.write_securities(root, ["EUR"])
            rates = refresh_currency_table(
                table, trades_file=trades_file, securities_file=securities_file
            )
            self.assertEqual(rates[0].valid_from, datetime(2025, 1, 14, tzinfo=timezone.utc))
            self.assertEqual(rates[-1].valid_to, datetime(2025, 1, 17, tzinfo=timezone.utc))
            trades = pd.DataFrame({"trade_id": [1, 2], "side": ["BUY", "SELL"],
                "isin": ["ONE", "ONE"], "quantity": [2., 2.],
                "price": [10., 10.], "trade_value": [20., 20.],
                "timestamp_trade_date": pd.to_datetime(["2025-01-14T23:00:00Z", "2025-01-16T23:59:59Z"], utc=True)})
            securities = pd.DataFrame({"isin": ["ONE"], "currency": ["EUR"]})
            currencies = pipeline.apply_semantics(pd.read_csv(table), pipeline.CURRENCY_SCHEMA)
            silver = pipeline.enrich_silver(trades, securities, currencies)
            self.assertTrue(silver["is_quality_valid"].all())
            self.assertEqual(silver["trade_value_usd"].tolist(), [22., 24.])
            self.assertEqual(mock_get.call_args.kwargs["params"]["to"], "2025-01-16")

    def test_invalid_or_empty_trade_timestamps_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            trades = Path(directory) / "trades.xml"
            for xml in ["<trades/>", "<trades><trade/></trades>",
                        "<trades><trade><tradeDate>invalid</tradeDate></trade></trades>"]:
                trades.write_text(xml)
                with self.assertRaises(ValueError):
                    fx_api.trade_date_range(trades)

    @patch.object(fx_api.httpx, "get")
    def test_refresh_writes_five_decimal_daily_references_for_requested_window(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = [
            {"date": "2026-10-27", "rate": "1.123456"},
            {"date": "2026-10-28", "rate": "1.123454"},
        ]
        mock_get.return_value = response
        now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / "currencies.csv"
            table.write_text("currency,fx_rate_to_usd,valid_from,valid_to\nUSD,1,,\nEUR,1,,\n")
            securities_file = self.write_securities(root, ["USD", "EUR"])
            rates = refresh_currency_table(table, now=now, securities_file=securities_file)
            written = pd.read_csv(table, dtype="string")

        rates_by_currency = {rate.currency: rate for rate in rates}
        written_by_currency = written.set_index("currency")
        self.assertEqual(rates_by_currency["USD"].fx_rate_to_usd, Decimal("1.00000"))
        self.assertEqual(rates_by_currency["EUR"].fx_rate_to_usd, Decimal("1.12346"))
        self.assertEqual(written_by_currency.loc["EUR", "fx_rate_to_usd"], "1.12346")
        self.assertEqual(written_by_currency.loc["EUR", "valid_from"], "2026-10-27T12:00:00Z")
        self.assertEqual(written_by_currency.loc["EUR", "valid_to"], "2026-10-28T12:00:00Z")
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_get.call_args.args[0], FRANKFURTER_RATES_URL)
        self.assertEqual(mock_get.call_args.kwargs["params"]["base"], "EUR")

    @patch.object(fx_api.httpx, "get")
    def test_history_creates_one_rate_per_day(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = [
            {"date": "2025-01-01", "rate": "1.10"},
            {"date": "2025-01-02", "rate": "1.20"},
        ]
        mock_get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / "currencies.csv"
            table.write_text("currency,fx_rate_to_usd,valid_from,valid_to\nEUR,1,,\n")
            securities_file = self.write_securities(root, ["EUR"])
            rates = refresh_currency_table(
                table, start_date=datetime(2025, 1, 1).date(),
                end_date=datetime(2025, 1, 2).date(),
                securities_file=securities_file,
            )
        self.assertEqual([rate.fx_rate_to_usd for rate in rates], [Decimal("1.10000"), Decimal("1.20000")])
        self.assertEqual(rates[0].valid_from, datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(rates[1].valid_to, datetime(2025, 1, 3, tzinfo=timezone.utc))

    @patch.object(fx_api.httpx, "get")
    def test_missing_currency_table_is_bootstrapped_from_securities(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = [
            {"date": "2025-01-01", "rate": "1.10"},
        ]
        mock_get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            securities = root / "securities.csv"
            currencies = root / "currencies.csv"
            securities.write_text("isin,currency\nONE,EUR\nTWO,USD\n", encoding="utf-8")
            rates = refresh_currency_table(
                currencies, start_date=datetime(2025, 1, 1).date(),
                end_date=datetime(2025, 1, 1).date(), securities_file=securities,
            )
            written = pd.read_csv(currencies, dtype="string")
        self.assertEqual(len(rates), 2)
        self.assertEqual(written["currency"].tolist(), ["EUR", "USD"])

    @patch.object(fx_api.httpx, "get")
    def test_missing_publication_uses_previous_reference(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = [
            {"date": "2024-12-31", "base": "EUR", "quote": "USD", "rate": 1.04},
            {"date": "2025-01-02", "base": "EUR", "quote": "USD", "rate": 1.05},
        ]
        mock_get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / "currencies.csv"
            table.write_text("currency,fx_rate_to_usd,valid_from,valid_to\nEUR,1,,\n")
            securities_file = self.write_securities(root, ["EUR"])
            rates = refresh_currency_table(
                table, start_date=datetime(2025, 1, 1).date(), end_date=datetime(2025, 1, 2).date(),
                securities_file=securities_file,
            )
        self.assertEqual([rate.fx_rate_to_usd for rate in rates], [Decimal("1.04000"), Decimal("1.05000")])

    @patch.object(fx_api.httpx, "get")
    def test_currency_universe_always_comes_from_current_securities(self, mock_get: Mock):
        mock_get.return_value.json.return_value = [{"date": "2025-01-01", "rate": "0.70"}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / "currencies.csv"
            table.write_text("currency\nEUR\nGBP\n")
            securities_file = self.write_securities(root, [" cad ", "USD", "CAD", ""])
            rates = refresh_currency_table(
                table, start_date=datetime(2025, 1, 1).date(),
                end_date=datetime(2025, 1, 1).date(), securities_file=securities_file,
            )
            written = pd.read_csv(table)
        self.assertEqual([rate.currency for rate in rates], ["CAD", "USD"])
        self.assertEqual(written["currency"].tolist(), ["CAD", "USD"])
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_get.call_args.kwargs["params"]["base"], "CAD")

    def test_security_master_must_supply_usable_currencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / "currencies.csv"
            for contents, message in [
                ("isin\nONE\n", "no currency column"),
                ("isin,currency\nONE,\n", "no usable currencies"),
            ]:
                securities = root / "securities.csv"
                securities.write_text(contents)
                with self.assertRaisesRegex(ValueError, message):
                    refresh_currency_table(
                        table, start_date=datetime(2025, 1, 1).date(),
                        end_date=datetime(2025, 1, 1).date(), securities_file=securities,
                    )

    def test_atomic_write_preserves_existing_table_on_serialization_failure(self):
        frame = pd.DataFrame({"currency": ["EUR"]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / "currencies.csv"
            table.write_text("currency\nUSD\n")
            original = table.read_bytes()
            error = OSError("disk full")

            def fail_write(dataframe, path, **kwargs):
                Path(path).write_text("partial")
                raise error

            with patch.object(pd.DataFrame, "to_csv", fail_write):
                with self.assertLogs(fx_api.LOGGER, level="ERROR"):
                    with self.assertRaises(fx_api.CurrencyTableWriteError) as caught:
                        fx_api.write_currency_table(frame, table)

            self.assertIs(caught.exception.__cause__, error)
            self.assertEqual(table.read_bytes(), original)
            self.assertEqual(list(root.iterdir()), [table])

    def test_atomic_write_preserves_existing_table_on_replace_failure(self):
        frame = pd.DataFrame({"currency": ["EUR"]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / "currencies.csv"
            table.write_text("currency\nUSD\n")
            original = table.read_bytes()
            with patch.object(Path, "replace", side_effect=PermissionError("locked")):
                with self.assertLogs(fx_api.LOGGER, level="ERROR"):
                    with self.assertRaisesRegex(fx_api.CurrencyTableWriteError, "locked"):
                        fx_api.write_currency_table(frame, table)
            self.assertEqual(table.read_bytes(), original)
            self.assertEqual(list(root.iterdir()), [table])


if __name__ == "__main__":
    unittest.main()
