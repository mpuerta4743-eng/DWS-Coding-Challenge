"""Opt-in live connectivity check; does not modify pipeline datasets."""

from datetime import date
from decimal import Decimal
from importlib import import_module
import os
from pathlib import Path
import sys
import unittest


fx_api = import_module("data_pipeline.fx_api")


@unittest.skipUnless(os.environ.get("RUN_FX_CONNECTIVITY_TESTS") == "1",
                     "Set RUN_FX_CONNECTIVITY_TESTS=1 to call Frankfurter")
class FxConnectivityTests(unittest.TestCase):
    def test_frankfurter_returns_usable_historical_rates(self):
        # A fixed historical business day keeps this independent of market holidays today.
        requested_date = date(2025, 1, 15)
        rates = fx_api._daily_reference_rates("EUR", requested_date, requested_date)
        self.assertIn(requested_date, rates)
        rate = rates[requested_date]
        self.assertIsInstance(rate, Decimal)
        self.assertTrue(rate.is_finite())
        self.assertGreater(rate, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
