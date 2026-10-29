# DWS Trade Analytics dashboard

An independent Streamlit application for daily activity by security and trader. It reads enriched trade-level Parquet; it does not run ingestion or transformation.

## Run locally

From the repository root:

```powershell
python -m pip install .
trade-dashboard
trade-dashboard --port 8502
trade-dashboard --trades-path C:\data\trades_enriched.parquet
```

The installed command uses the active Python environment, packaged dashboard source and theme. The same installation includes all pipeline and dashboard dependencies. It does not modify datasets.

## Data source

From this checkout, the default source is data_pipeline/data/1_silver/trades_enriched.parquet. For an installed package used elsewhere, set DWS_DATA_ROOT to a directory containing data/1_silver/, or override the complete source path:

```powershell
$env:DWS_TRADES_PATH = "C:\data\trades_enriched.parquet"
# Alternatively, a root containing data/1_silver/:
$env:DWS_DATA_ROOT = "C:\trade-producer"
```

DWS_TRADES_PATH takes precedence. Required columns are defined in trade_analytics.py. The contract uses uppercase datatype prefixes, including INT_TRADE_ID, INT_QUANTITY, STRING_INSTRUMENT and FLOAT_TRADE_VALUE_USD. External or Gold producers must preserve the trade-level contract; aggregated tables do not satisfy it. Missing or incompatible files produce an English error.

## Features and metrics

The English interface uses a light navy/teal theme, daily KPIs, 30-minute activity, BUY/SELL breakdowns, security/trader rankings, global filters, and a searchable trade explorer with CSV download. Explorer search affects only its table and download.

The latest available trading date opens in UTC. Rankings support counts or gross USD value (sum of available absolute values). Flagged trades stay in counts. Missing valuations are reported and excluded only from value sums, without replacing them with zero. Invalid timestamps are reported separately. Quantities across different instruments are not summed.

One day shows intraday trends. With more history, counts are compared with the previous available day under the same filters. Processing timestamps identify dataset refresh time.

See [test responsibilities](../tests/README.md) and [installation and commands](../README.md).
