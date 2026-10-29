"""Bronze -> Silver with separate reading, transformation and enrichment stages."""

from __future__ import annotations

import argparse
import logging
from contextlib import contextmanager
from time import perf_counter
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from .settings import data_root
from .schemas import CURRENCY_SCHEMA, SECURITY_SCHEMA, TRADE_SCHEMA, DatasetSchema
from .silver_semantics import semanticize_silver, validate_silver_names


LOGGER = logging.getLogger(__name__)


@contextmanager
def log_stage(name: str):
    started = perf_counter()
    LOGGER.info("START %s", name)
    try:
        yield
    except Exception:
        LOGGER.exception("FAILED %s after %.3fs", name, perf_counter() - started)
        raise
    LOGGER.info("DONE %s in %.3fs", name, perf_counter() - started)


class SilverWriteError(RuntimeError):
    """Publication failed; the original exception is preserved as the cause."""


def write_parquet(silver: pd.DataFrame, path: Path) -> None:
    """Write in isolation and replace the destination only after serialization succeeds."""
    temporary = None
    started = perf_counter()
    LOGGER.info("Writing Parquet: %s; rows=%s columns=%s", path, len(silver), len(silver.columns))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.stem}-", suffix=".parquet", delete=False) as handle:
            temporary = Path(handle.name)
        silver.to_parquet(temporary, index=False)
        size = temporary.stat().st_size
        temporary.replace(path)
    except Exception as error:
        LOGGER.exception("Parquet write FAILED: %s; rows=%s columns=%s; %s: %s",
                         path, len(silver), len(silver.columns), type(error).__name__, error)
        raise SilverWriteError(f"Cannot write Parquet {path}: {type(error).__name__}: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Could not remove temporary Parquet %s", temporary, exc_info=True)
    LOGGER.info("Parquet written: %s; bytes=%s; elapsed=%.3fs", path, size, perf_counter() - started)


def clean_text_values(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim and uppercase textual values; preserve nulls and non-text types."""
    result = frame.copy()
    for name in result.columns:
        column = result[name]
        if isinstance(column.dtype, pd.StringDtype):
            result[name] = column.str.strip().str.upper()
        elif pd.api.types.is_object_dtype(column.dtype):
            result[name] = column.map(
                lambda value: value.strip().upper() if isinstance(value, str) else value
            )
    return result


def parse_utc_datetime(values: pd.Series) -> pd.Series:
    """Parse mixed ISO-8601 timestamp representations into UTC."""
    return pd.to_datetime(values, format="mixed", errors="coerce", utc=True)


def finite_numeric(values: pd.Series) -> pd.Series:
    """Identify non-null numeric values that are neither positive nor negative infinity."""
    return values.notna() & values.abs().lt(float("inf"))


def apply_semantics(frame: pd.DataFrame, schema: DatasetSchema) -> pd.DataFrame:
    """Select required columns, rename them and apply schema types."""
    schema.validate()
    missing = sorted(set(schema.source_columns) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    result = frame.loc[:, list(schema.source_columns)].copy()
    result.columns = list(schema.silver_columns)
    result = clean_text_values(result)
    for column, dtype in zip(schema.silver_columns, schema.dtypes, strict=True):
        if dtype == "datetime_utc":
            result[column] = parse_utc_datetime(result[column])
        elif dtype in {"Int64", "Float64"}:
            result[column] = pd.to_numeric(result[column], errors="coerce").astype(dtype)
        else:
            result[column] = result[column].astype(dtype)
    return result


def semanticize_bronze(
    bronze_trades: pd.DataFrame,
    bronze_securities: pd.DataFrame,
    bronze_currencies: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply semantic names and types without joins or business calculations."""
    return (
        apply_semantics(bronze_trades, TRADE_SCHEMA),
        apply_semantics(bronze_securities, SECURITY_SCHEMA),
        apply_semantics(bronze_currencies, CURRENCY_SCHEMA),
    )


def transform_silver(
    bronze_trades: pd.DataFrame,
    bronze_securities: pd.DataFrame,
    bronze_currencies: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Normalize names/types and calculate local values, without joins or I/O."""
    trades, securities, currencies = semanticize_bronze(
        bronze_trades, bronze_securities, bronze_currencies
    )
    trade_value = (trades["quantity"] * trades["price"]).astype("Float64")
    valid_inputs = finite_numeric(trades["quantity"]) & finite_numeric(trades["price"])
    trades["trade_value"] = trade_value.mask(
        ~valid_inputs | ~finite_numeric(trade_value), pd.NA
    ).astype("Float64")
    return trades, securities, currencies


def enrich_silver(
    trades: pd.DataFrame,
    securities: pd.DataFrame,
    currencies: pd.DataFrame,
) -> pd.DataFrame:
    """Join reference data, calculate USD values and flag quality, without I/O."""
    # Missing identifiers must never match each other during a pandas merge.
    securities = securities.loc[securities["isin"].notna() & securities["isin"].ne("")]
    currency_conflicts = securities.groupby("isin", dropna=False)["currency"].nunique(
        dropna=False
    )
    conflicting_isins = currency_conflicts[currency_conflicts > 1].index.tolist()
    if conflicting_isins:
        raise ValueError(f"Conflicting currencies for ISIN: {conflicting_isins}")
    securities = securities.drop_duplicates(subset=["isin"], keep="first")

    silver = trades.merge(
        securities[["isin", "currency"]],
        on="isin",
        how="left",
        validate="many_to_one",
        indicator="security_join",
    )

    silver["has_security"] = silver["security_join"].eq("both").astype("boolean")
    LOGGER.info("Security join: input=%s output=%s matched=%s unmatched=%s",
                len(trades), len(silver), int(silver["has_security"].sum()), int((~silver["has_security"]).sum()))

    rates = currencies[["currency", "fx_rate_to_usd", "valid_from", "valid_to"]].copy()
    invalid_rate_window = (
        rates["valid_from"].isna()
        | rates["valid_to"].isna()
        | rates["valid_from"].ge(rates["valid_to"])
    )
    if invalid_rate_window.any():
        raise ValueError("currencies.csv contains invalid validity windows")
    rates = rates.sort_values(["currency", "valid_from"])
    overlapping_rate_window = rates.groupby("currency")["valid_to"].shift().gt(rates["valid_from"])
    if overlapping_rate_window.any():
        raise ValueError("currencies.csv contains overlapping validity windows")

    silver["_trade_row"] = range(len(silver))
    candidates = silver[["_trade_row", "currency", "timestamp_trade_date"]].merge(
        rates, on="currency", how="left", validate="many_to_many"
    )
    applicable_rates = candidates.loc[
        candidates["timestamp_trade_date"].ge(candidates["valid_from"])
        & candidates["timestamp_trade_date"].lt(candidates["valid_to"])
    ]
    if applicable_rates["_trade_row"].duplicated().any():
        raise ValueError("More than one exchange rate applies to a trade")
    silver = silver.merge(
        applicable_rates[["_trade_row", "fx_rate_to_usd", "valid_from", "valid_to"]],
        on="_trade_row", how="left", validate="one_to_one"
    )

    has_applicable_rate = silver["valid_from"].notna()
    valid_fx_rate = finite_numeric(silver["fx_rate_to_usd"]) & silver["fx_rate_to_usd"].gt(0)
    usd_value = (silver["trade_value"] * silver["fx_rate_to_usd"]).astype("Float64")
    silver["trade_value_usd"] = usd_value.mask(
        ~finite_numeric(silver["trade_value"]) | ~valid_fx_rate | ~finite_numeric(usd_value),
        pd.NA,
    ).astype("Float64")

    if len(silver) != len(trades):
        raise ValueError("Enrichment must preserve exactly one row per input trade")

    LOGGER.info("FX join: output=%s rows_with_rate=%s rows_without_rate=%s",
                len(silver), int(silver["fx_rate_to_usd"].notna().sum()), int(silver["fx_rate_to_usd"].isna().sum()))
    security_missing = ~silver["has_security"]
    currency_missing = silver["has_security"] & (
        silver["currency"].isna() | silver["currency"].eq("")
    )
    invalid_value = (
        ~finite_numeric(silver["quantity"])
        | ~finite_numeric(silver["price"])
        | ~finite_numeric(silver["trade_value"])
        | (valid_fx_rate & ~finite_numeric(usd_value))
    )
    invalid_trade_date = silver["timestamp_trade_date"].isna()
    invalid_fx_rate = has_applicable_rate & ~valid_fx_rate
    trade_id_missing = silver["trade_id"].isna()
    duplicate_trade_id = silver["trade_id"].notna() & silver["trade_id"].duplicated(keep=False)
    invalid_side = ~silver["side"].isin(["BUY", "SELL"])
    currency_rate_missing = (
        silver["currency"].notna()
        & silver["currency"].ne("")
        & ~invalid_trade_date
        & ~has_applicable_rate
    )
    silver["quality_flags"] = ""
    silver.loc[security_missing, "quality_flags"] += "SECURITY_NOT_FOUND;"
    silver.loc[currency_missing, "quality_flags"] += "CURRENCY_MISSING;"
    silver.loc[invalid_value, "quality_flags"] += "INVALID_TRADE_VALUE;"
    silver.loc[invalid_trade_date, "quality_flags"] += "INVALID_TRADE_DATE;"
    silver.loc[invalid_fx_rate, "quality_flags"] += "INVALID_FX_RATE;"
    silver.loc[trade_id_missing, "quality_flags"] += "TRADE_ID_MISSING;"
    silver.loc[duplicate_trade_id, "quality_flags"] += "DUPLICATE_TRADE_ID;"
    silver.loc[invalid_side, "quality_flags"] += "INVALID_SIDE;"
    silver.loc[currency_rate_missing, "quality_flags"] += "CURRENCY_RATE_NOT_VALID_FOR_TRADE;"
    silver["quality_flags"] = silver["quality_flags"].str.rstrip(";").astype("string")
    silver["is_quality_valid"] = silver["quality_flags"].eq("").astype("boolean")
    return silver.drop(columns=["security_join", "_trade_row", "valid_from", "valid_to"])


def read_trades_xml(path: Path) -> pd.DataFrame:
    """Read the original exercise file without modifying Bronze."""
    root = ET.parse(path).getroot()
    return pd.DataFrame([
        {child.tag: (child.text or "") for child in trade}
        for trade in root.findall("trade")
    ]).dropna(how="all")


def read_bronze(bronze_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read source data and record ingestion time, without business transformations."""
    required = {
        "trades": bronze_dir / "trades.xml",
        "securities": bronze_dir / "securities.csv",
        "currencies": bronze_dir / "currencies.csv",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Bronze files not found: {missing}")

    bronze_frames = {}
    for name, path in required.items():
        LOGGER.info("Reading %s: %s", name, path)
        bronze_frames[name] = read_trades_xml(path) if name == "trades" else pd.read_csv(path, dtype="string")
        LOGGER.info("Read %s: rows=%s columns=%s", name, len(bronze_frames[name]), len(bronze_frames[name].columns))
    bronze_frames["trades"]["timestamp_file_processed"] = pd.Timestamp.now(tz="UTC")
    return (
        bronze_frames["trades"], bronze_frames["securities"], bronze_frames["currencies"]
    )


def write_silver(
    silver: pd.DataFrame, silver_dir: Path, *, table_name: str = "trades_enriched",
) -> None:
    """Publish any semanticized Silver table without transforming it."""
    validate_silver_names(silver)
    if not table_name or not all(char.isalnum() or char == "_" for char in table_name):
        raise ValueError("table_name must contain only letters, digits and underscores")
    write_parquet(silver, silver_dir / f"{table_name}.parquet")



def run_bronze_to_silver(bronze_dir: Path, silver_dir: Path) -> pd.DataFrame:
    """Orchestrate reading, transformation, enrichment and publication in order."""
    started = perf_counter()
    LOGGER.info("Bronze -> Silver started: source=%s destination=%s", bronze_dir, silver_dir)
    with log_stage("Read Bronze"):
        bronze_frames = read_bronze(bronze_dir)
    with log_stage("Clean, normalize types and calculate local trade values"):
        transformed_frames = transform_silver(*bronze_frames)
    with log_stage("Enrich securities and FX; calculate quality flags"):
        enriched = enrich_silver(*transformed_frames)
    with log_stage("Apply uppercase Silver datatype names"):
        silver = semanticize_silver(clean_text_values(enriched))
        LOGGER.info("Silver schema: %s", {name: str(dtype) for name, dtype in silver.dtypes.items()})
    with log_stage("Publish Silver"):
        write_silver(silver, silver_dir)
    LOGGER.info("Bronze -> Silver completed: trades=%s quality_flagged=%s elapsed=%.3fs",
                len(silver), int((~silver["BOOLEAN_IS_QUALITY_VALID"]).sum()), perf_counter() - started)
    return silver


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="Run isolated transformation, enrichment, naming and publication checks")
    args = parser.parse_args()
    if args.test:
        from .testing import run_unit_checks
        raise SystemExit(run_unit_checks("transform"))
    root = data_root()
    try:
        run_bronze_to_silver(root / "data" / "0_bronze", root / "data" / "1_silver")
    except Exception as error:
        LOGGER.error("Pipeline failed: %s: %s", type(error).__name__, error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
