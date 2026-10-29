"""Positional semantic column names and types for source tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DatasetSchema:
    source_columns: Sequence[str]
    silver_columns: Sequence[str]
    dtypes: Sequence[str]

    def validate(self) -> None:
        lengths = {len(self.source_columns), len(self.silver_columns), len(self.dtypes)}
        if len(lengths) != 1:
            raise ValueError("source_columns, silver_columns and dtypes must have equal lengths")
        if len(set(self.source_columns)) != len(self.source_columns):
            raise ValueError("source_columns contains duplicate names")
        if len(set(self.silver_columns)) != len(self.silver_columns):
            raise ValueError("silver_columns contains duplicate names")


TRADE_SCHEMA = DatasetSchema(
    source_columns=[
        "tradeId", "orderId", "traderId", "account", "strategy", "tradeType",
        "instrument", "isin", "quantity", "price", "side", "tradeDate",
        "timestamp_file_processed",
    ],
    silver_columns=[
        "trade_id", "order_id", "trader_id", "account", "strategy", "trade_type",
        "instrument", "isin", "quantity", "price", "side", "timestamp_trade_date",
        "timestamp_file_processed",
    ],
    dtypes=[
        "Int64", "Int64", "string", "string", "string", "string",
        "string", "string", "Int64", "Float64", "string", "datetime_utc",
        "datetime_utc",
    ],
)

SECURITY_SCHEMA = DatasetSchema(
    source_columns=["isin", "currency"],
    silver_columns=["isin", "currency"],
    dtypes=["string", "string"],
)

CURRENCY_SCHEMA = DatasetSchema(
    source_columns=["currency", "fx_rate_to_usd", "valid_from", "valid_to"],
    silver_columns=["currency", "fx_rate_to_usd", "valid_from", "valid_to"],
    dtypes=["string", "Float64", "datetime_utc", "datetime_utc"],
)
