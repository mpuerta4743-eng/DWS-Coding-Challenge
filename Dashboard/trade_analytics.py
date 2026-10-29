"""Data contract and aggregations shared by the Streamlit dashboard."""
from pathlib import Path

import pandas as pd

REQUIRED = {
    "INT_TRADE_ID", "STRING_TRADER_ID", "STRING_INSTRUMENT", "STRING_ISIN", "INT_QUANTITY", "STRING_SIDE",
    "TIMESTAMP_TRADE_DATE", "FLOAT_TRADE_VALUE_USD", "BOOLEAN_IS_QUALITY_VALID",
    "STRING_QUALITY_FLAGS", "STRING_STRATEGY", "STRING_ACCOUNT", "STRING_CURRENCY", "STRING_TRADE_TYPE",
}


def resolve_source(root: Path, override: str = "") -> Path:
    """Resolve the Silver Parquet or an explicitly configured source."""
    if override:
        path = Path(override).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Trade source does not exist: {path}")
        return path
    path = root / "data" / "1_silver" / "trades_enriched.parquet"
    if path.is_file():
        return path
    raise FileNotFoundError("No trade Parquet found. Set DWS_TRADES_PATH to an existing enriched Parquet source, or configure DWS_DATA_ROOT.")


def load_trades(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(
            f"Trade source {path.resolve()} is missing required columns: "
            f"{', '.join(sorted(missing))}. "
            f"Available columns: {', '.join(map(str, frame.columns)) or '(none)'}"
        )
    frame["TIMESTAMP_TRADE_DATE"] = pd.to_datetime(frame["TIMESTAMP_TRADE_DATE"], utc=True, errors="coerce")
    for col in ("INT_QUANTITY", "FLOAT_TRADE_VALUE_USD"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame[col] = frame[col].where(frame[col].abs().lt(float("inf")))
    frame["FLOAT_GROSS_VALUE_USD"] = frame["FLOAT_TRADE_VALUE_USD"].abs()
    frame["STRING_QUALITY_FLAGS"] = frame["STRING_QUALITY_FLAGS"].fillna("")
    frame["BOOLEAN_FLAGGED"] = ~frame["BOOLEAN_IS_QUALITY_VALID"].astype("string").str.lower().eq("true").fillna(False)
    frame["BOOLEAN_FLAGGED"] |= frame["STRING_QUALITY_FLAGS"].ne("")
    frame["STRING_SIDE"] = frame["STRING_SIDE"].astype("string").str.upper().fillna("UNKNOWN")
    for col in ("STRING_TRADER_ID", "STRING_INSTRUMENT", "STRING_ISIN", "STRING_STRATEGY", "STRING_ACCOUNT", "STRING_CURRENCY", "STRING_TRADE_TYPE"):
        frame[col] = frame[col].astype("string").fillna("Unknown")
    return frame


def summarize(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return frame.groupby(keys, dropna=False).agg(
        Trades=("INT_TRADE_ID", "size"),
        Gross_USD=("FLOAT_GROSS_VALUE_USD", lambda s: s.sum(min_count=1)),
        Missing_USD=("FLOAT_GROSS_VALUE_USD", lambda s: s.isna().sum()),
        Flagged=("BOOLEAN_FLAGGED", "sum"),
    ).reset_index()

