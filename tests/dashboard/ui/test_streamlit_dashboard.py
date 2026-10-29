from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

import pandas as pd

from streamlit.testing.v1 import AppTest


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        source = Path(self.temp.name) / "trades.parquet"
        pd.DataFrame({
            "INT_TRADE_ID": [1, 2, 3], "STRING_TRADER_ID": ["trader1", "trader2", "trader1"],
            "STRING_INSTRUMENT": ["ABC", "XYZ", "ABC"], "STRING_ISIN": ["I1", "I2", "I1"],
            "INT_QUANTITY": [2, 3, 4], "STRING_SIDE": ["BUY", "SELL", "BUY"],
            "TIMESTAMP_TRADE_DATE": ["2025-01-15T09:00:00Z", "2025-01-15T10:00:00Z", "2025-01-15T11:00:00Z"],
            "FLOAT_TRADE_VALUE_USD": [20, None, 30], "BOOLEAN_IS_QUALITY_VALID": [True, False, True],
            "STRING_QUALITY_FLAGS": ["", "missing_fx", ""], "STRING_STRATEGY": ["s1"] * 3,
            "STRING_ACCOUNT": ["a1"] * 3, "STRING_CURRENCY": ["USD"] * 3, "STRING_TRADE_TYPE": ["Normal"] * 3,
        }).to_parquet(source)
        env = patch.dict("os.environ", {"DWS_TRADES_PATH": str(source)})
        env.start()
        self.addCleanup(env.stop)

    def test_dashboard_filters_and_ranking(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[3] / "Dashboard" / "streamlit_app.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "3")
        app.radio[0].set_value("Gross traded value (USD)").run()
        self.assertFalse(app.exception)
        app.multiselect[1].set_value(["trader1"]).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[3].value, "1")
        app.text_input[0].set_value("no-such-trade").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[-1].value), 0)
        app.multiselect[0].set_value(["XYZ"]).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.info)

