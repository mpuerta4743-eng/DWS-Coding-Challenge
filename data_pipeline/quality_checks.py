"""Read-only quality checks for the published enriched Parquet dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .settings import data_root


DEFAULT_PARQUET = data_root() / "data" / "1_silver" / "trades_enriched.parquet"


def check_enriched_parquet(path: Path = DEFAULT_PARQUET) -> dict[str, int]:
    """Count failures against persisted data, without cleaning or dropping rows."""
    frame = pd.read_parquet(path)
    required = {
        "BOOLEAN_HAS_SECURITY", "BOOLEAN_IS_QUALITY_VALID", "FLOAT_TRADE_VALUE_USD",
        "INT_TRADE_ID", "STRING_QUALITY_FLAGS", "STRING_SIDE",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required quality columns: {missing}")
    if not pd.api.types.is_bool_dtype(frame["BOOLEAN_HAS_SECURITY"].dtype):
        raise TypeError("BOOLEAN_HAS_SECURITY must have boolean dtype")
    if not pd.api.types.is_bool_dtype(frame["BOOLEAN_IS_QUALITY_VALID"].dtype):
        raise TypeError("BOOLEAN_IS_QUALITY_VALID must have boolean dtype")
    ids = frame["INT_TRADE_ID"]
    duplicate_rows = ids.notna() & ids.duplicated(keep=False)
    usd_values = pd.to_numeric(frame["FLOAT_TRADE_VALUE_USD"], errors="coerce")
    invalid_quality = (
        frame["BOOLEAN_IS_QUALITY_VALID"].fillna(False).ne(True)
        | frame["STRING_QUALITY_FLAGS"].fillna("").ne("")
    )
    return {
        "total_trades": len(frame),
        "trades_without_security": int(frame["BOOLEAN_HAS_SECURITY"].eq(False).sum()),
        "null_security_flags": int(frame["BOOLEAN_HAS_SECURITY"].isna().sum()),
        "duplicate_trade_id_rows": int(duplicate_rows.sum()),
        "duplicate_trade_ids": int(ids[duplicate_rows].nunique()),
        "null_trade_ids": int(ids.isna().sum()),
        "invalid_side_rows": int((~frame["STRING_SIDE"].isin(["SELL", "BUY"])).sum()),
        "invalid_quality_rows": int(invalid_quality.sum()),
        "invalid_usd_value_rows": int((usd_values.isna() | usd_values.abs().ge(float("inf"))).sum()),
    }


def quality_passed(report: dict[str, int]) -> bool:
    return all(count == 0 for name, count in report.items() if name != "total_trades")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PARQUET)
    args = parser.parse_args(argv)
    report = check_enriched_parquet(args.path)
    print(f"Parquet quality report: {args.path}")
    for name, count in report.items():
        print(f"{name}: {count}")
    passed = quality_passed(report)
    print("PASS" if passed else "FAIL")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
