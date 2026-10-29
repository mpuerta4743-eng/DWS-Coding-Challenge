"""Small local Bronze fixtures shared by pipeline stage tests."""
import pandas as pd


class BronzeFixtureMixin:
    def setUp(self) -> None:
        timestamp = "2026-10-28T10:00:00+00:00"
        self.trades = pd.DataFrame(
            [{
                "tradeId": "1", "orderId": "10", "traderId": "trader1",
                "account": "acc1", "strategy": "s1", "tradeType": "Regular",
                "instrument": "ABC", "isin": "KNOWN", "quantity": "2",
                "price": "10.5", "side": "BUY", "tradeDate": "2025-01-15T09:00:00Z",
                "timestamp_file_processed": timestamp,
            }]
        )
        self.securities = pd.DataFrame(
            [{"isin": "KNOWN", "currency": "EUR", "timestamp_file_processed": timestamp}]
        )
        self.currencies = pd.DataFrame(
            [{
                "currency": "EUR", "fx_rate_to_usd": "1.1",
                "valid_from": "2025-01-15T00:00:00Z", "valid_to": "2025-01-16T00:00:00Z",
                "timestamp_file_processed": timestamp,
            }]
        )

