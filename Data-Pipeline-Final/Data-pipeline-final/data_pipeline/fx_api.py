"""HTTP API to refresh the currency input table from Frankfurter daily reference rates."""

from __future__ import annotations

import argparse
import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


from .settings import data_root


ROOT = data_root()
DEFAULT_CURRENCIES_FILE = ROOT / "data" / "0_bronze" / "currencies.csv"
DEFAULT_TRADES_FILE = ROOT / "data" / "0_bronze" / "trades.xml"
DEFAULT_SECURITIES_FILE = ROOT / "data" / "0_bronze" / "securities.csv"
FRANKFURTER_RATES_URL = "https://api.frankfurter.dev/v2/rates"
RATE_PRECISION = Decimal("0.00001")
LOGGER = logging.getLogger(__name__)


class CurrencyRate(BaseModel):
    currency: str
    fx_rate_to_usd: Decimal
    valid_from: datetime
    valid_to: datetime


class RefreshResult(BaseModel):
    rates: list[CurrencyRate]
    written_to: str


class CurrencyTableWriteError(RuntimeError):
    """Currency-table publication failed without replacing the prior table."""


def trade_date_range(trades_file: Path) -> tuple[date, date]:
    """Find the inclusive UTC date range required by the source trades."""
    try:
        root = ET.parse(trades_file).getroot()
    except ET.ParseError as error:
        raise ValueError(f"Invalid trades XML: {trades_file}") from error
    values = [trade.findtext("tradeDate") for trade in root.findall("trade")]
    if not values:
        raise ValueError("No trades found; cannot infer the FX date range")
    timestamps = pd.to_datetime(pd.Series(values), utc=True, errors="coerce", format="mixed")
    if timestamps.isna().any():
        raise ValueError("Missing or invalid tradeDate; cannot infer the FX date range")
    return timestamps.min().date(), timestamps.max().date()


def _daily_reference_rates(currency: str, start: date, end: date) -> dict[date, Decimal]:
    """Fetch no-key daily reference rates for CURRENCY/USD from Frankfurter."""
    if currency == "USD":
        return {current: Decimal("1") for current in pd.date_range(start, end, freq="D").date}

    LOGGER.info("Requesting daily %s/USD reference rates from %s to %s", currency, start, end)
    response = httpx.get(
        FRANKFURTER_RATES_URL,
        params={"base": currency, "quotes": "USD", "from": start.isoformat(), "to": end.isoformat()},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"No daily reference data returned for {currency}/USD")
    rates = {date.fromisoformat(point["date"]): Decimal(str(point["rate"])) for point in payload}
    LOGGER.info("Received %s daily observations for %s/USD", len(rates), currency)
    return rates


def _currencies_to_refresh(securities_file: Path) -> list[str]:
    """Derive the required currency universe from the current security master."""
    if not securities_file.is_file():
        raise FileNotFoundError(f"Securities input is unavailable: {securities_file}")
    securities = pd.read_csv(securities_file, dtype="string")
    if "currency" not in securities:
        raise ValueError(f"Security master has no currency column: {securities_file}")
    currencies = sorted(
        securities["currency"].dropna().str.strip().str.upper().loc[lambda values: values.ne("")].unique()
    )
    if not currencies:
        raise ValueError(f"Security master has no usable currencies: {securities_file}")
    LOGGER.info("Loaded %s required currencies from %s", len(currencies), securities_file)
    return currencies


def write_currency_table(frame: pd.DataFrame, path: Path) -> None:
    """Serialize beside the destination and replace it only after a complete write."""
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.stem}-", suffix=".csv", delete=False
        ) as handle:
            temporary = Path(handle.name)
        frame.to_csv(temporary, index=False)
        temporary.replace(path)
    except Exception as error:
        LOGGER.exception("Currency table write FAILED: %s; %s: %s", path, type(error).__name__, error)
        raise CurrencyTableWriteError(
            f"Cannot write currency table {path}: {type(error).__name__}: {error}"
        ) from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Could not remove temporary currency table %s", temporary, exc_info=True)


def refresh_currency_table(
    currencies_file: Path = DEFAULT_CURRENCIES_FILE,
    now: datetime | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    trades_file: Path = DEFAULT_TRADES_FILE,
    securities_file: Path | None = None,
) -> list[CurrencyRate]:
    """Cover source trade dates by default; explicit dates override the inferred range."""
    securities_file = securities_file or DEFAULT_SECURITIES_FILE
    currencies = _currencies_to_refresh(securities_file)
    if (start_date is None) != (end_date is None):
        raise ValueError("start_date and end_date must be supplied together")
    if start_date and end_date and end_date < start_date:
        raise ValueError("end_date must not be before start_date")

    if start_date is None and now is None:
        start_date, end_date = trade_date_range(trades_file)

    if start_date:
        windows = [
            (
                datetime.combine(start_date + timedelta(days=offset), time.min, tzinfo=timezone.utc),
                datetime.combine(start_date + timedelta(days=offset + 1), time.min, tzinfo=timezone.utc),
            )
            for offset in range((end_date - start_date).days + 1)
        ]
    else:
        end = now.astimezone(timezone.utc)
        windows = [(end - timedelta(hours=24), end)]

    LOGGER.info(
        "Starting Frankfurter FX refresh: %s currencies, %s validity windows, %s to %s",
        len(currencies), len(windows), windows[0][0], windows[-1][1],
    )
    rates: list[CurrencyRate] = []
    request_start, request_end = windows[0][0], windows[-1][1]
    for currency in currencies:
        LOGGER.info("Selecting daily FX reference rates for %s", currency)
        daily_rates = _daily_reference_rates(
            currency, request_start.date() - timedelta(days=7),
            (request_end - timedelta(microseconds=1)).date(),
        )
        for valid_from, valid_to in windows:
            eligible_dates = [observed for observed in daily_rates if observed <= valid_from.date()]
            if not eligible_dates:
                raise ValueError(f"No daily reference rate for {currency}/USD on {valid_from.date()}")
            rate = daily_rates[max(eligible_dates)]
            rates.append(CurrencyRate(
                currency=currency,
                fx_rate_to_usd=rate.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP),
                valid_from=valid_from,
                valid_to=valid_to,
            ))
    write_currency_table(
        pd.DataFrame([rate.model_dump(mode="json") for rate in rates]), currencies_file
    )
    LOGGER.info("FX refresh complete: wrote %s rates to %s", len(rates), currencies_file)
    return rates


app = FastAPI(title="Currency rate service", version="1.0.0")


@app.post("/currency-rates/refresh", response_model=RefreshResult)
def refresh_rates() -> RefreshResult:
    """Refresh daily reference rates covering all source trade timestamps."""
    try:
        rates = refresh_currency_table()
    except (OSError, ValueError, CurrencyTableWriteError, httpx.HTTPError) as error:
        LOGGER.exception("Current FX refresh failed")
        raise HTTPException(status_code=502, detail=str(error)) from error
    return RefreshResult(rates=rates, written_to=str(DEFAULT_CURRENCIES_FILE))


@app.post("/currency-rates/refresh-history", response_model=RefreshResult)
def refresh_historical_rates(start_date: date, end_date: date) -> RefreshResult:
    """Create daily 24-hour rate windows, inclusive, for a historical date range."""
    try:
        rates = refresh_currency_table(start_date=start_date, end_date=end_date)
    except (OSError, ValueError, CurrencyTableWriteError, httpx.HTTPError) as error:
        LOGGER.exception("Historical FX refresh failed")
        raise HTTPException(status_code=502, detail=str(error)) from error
    return RefreshResult(rates=rates, written_to=str(DEFAULT_CURRENCIES_FILE))


def main() -> None:
    """Ingest rates covering the source trades, or serve the HTTP API."""
    parser = argparse.ArgumentParser(description="Refresh daily currency reference rates from Frankfurter")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--serve", action="store_true", help="Start the FastAPI server instead of ingesting")
    mode.add_argument("--test", action="store_true", help="Run isolated exchange-rate unit checks from the source checkout")
    parser.add_argument("--start-date", type=date.fromisoformat, help="Optional historical start date")
    parser.add_argument("--end-date", type=date.fromisoformat, help="Optional historical end date")
    args = parser.parse_args()
    if args.test:
        if args.start_date or args.end_date:
            parser.error("--test cannot be combined with ingestion dates")
        from .testing import run_unit_checks
        raise SystemExit(run_unit_checks("api-usd-exchange-rates"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.serve:
        import uvicorn

        LOGGER.info("Starting FX API server at http://127.0.0.1:8000")
        uvicorn.run(app, host="127.0.0.1", port=8000)
        return

    LOGGER.info(
        "Running Frankfurter %s ingestion",
        f"from {args.start_date} to {args.end_date}" if args.start_date else "for the source trade date range",
    )
    try:
        refresh_currency_table(start_date=args.start_date, end_date=args.end_date)
    except (OSError, ValueError, CurrencyTableWriteError, httpx.HTTPError) as error:
        LOGGER.exception("FX ingestion failed: %s", error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
