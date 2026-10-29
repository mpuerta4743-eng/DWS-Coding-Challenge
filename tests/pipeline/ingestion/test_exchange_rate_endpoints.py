"""API endpoint functions use mocked ingestion and never call live providers."""
from datetime import date
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from data_pipeline import fx_api


class ExchangeRateEndpointTests(unittest.TestCase):
    @patch.object(fx_api, "refresh_currency_table", return_value=[])
    def test_current_refresh_delegates_to_ingestion(self, refresh):
        response = fx_api.refresh_rates()
        self.assertEqual(response.rates, [])
        refresh.assert_called_once_with()

    @patch.object(fx_api, "refresh_currency_table", return_value=[])
    def test_historical_dates_are_parsed_and_forwarded(self, refresh):
        response = fx_api.refresh_historical_rates(date(2025, 1, 1), date(2025, 1, 31))
        self.assertEqual(response.rates, [])
        refresh.assert_called_once_with(start_date=date(2025, 1, 1), end_date=date(2025, 1, 31))

    @patch.object(fx_api, "refresh_currency_table", side_effect=ValueError("Invalid rate window"))
    def test_ingestion_failure_returns_502(self, refresh):
        with self.assertLogs(fx_api.LOGGER, level="ERROR"):
            with self.assertRaises(HTTPException) as caught:
                fx_api.refresh_rates()
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(caught.exception.detail, "Invalid rate window")

    @patch.object(
        fx_api, "refresh_currency_table",
        side_effect=fx_api.CurrencyTableWriteError("destination locked"),
    )
    def test_atomic_publication_failure_returns_502(self, refresh):
        with self.assertLogs(fx_api.LOGGER, level="ERROR"):
            with self.assertRaises(HTTPException) as caught:
                fx_api.refresh_rates()
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(caught.exception.detail, "destination locked")
