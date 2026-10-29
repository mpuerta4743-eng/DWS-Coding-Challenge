# DWS Trade Analytics

This Python 3.12+ project processes a daily trade batch. It gets USD exchange rates from Frankfurter, transforms Bronze data into a Silver dataset, checks data quality, and shows the result in a Streamlit dashboard.

The project declares its dependencies and installed commands in `pyproject.toml`.

## Install the project

Run the installation from the repository root, where `pyproject.toml` is located.

If the PowerShell prompt already starts with `(.venv)`, the virtual environment is active. Do not create or activate another one. Confirm which Python executable is active, then install the project and its required packages into that environment:

```powershell
python -c "import sys; print(sys.executable)"
python -m pip install .
```

`python -m pip install .` installs this project, its command-line entry points, and the direct dependencies declared in `pyproject.toml`. Pip also installs supporting dependencies required by those libraries. It does not install every Python package available. This project declares both pipeline and dashboard dependencies, so the command installs both component sets.

Create a virtual environment only when one is not already active:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
```

The project requires Python 3.12 or newer. Check the selected interpreter with `python --version`. Installation normally needs to be run only once per virtual environment, and again after the dependency declarations change. For development, use an editable installation so source-code changes are immediately available:

```powershell
python -m pip install -e .
```

### Dependencies by component

| Component | Direct packages | Purpose |
| --- | --- | --- |
| Batch pipeline | `pandas`, `pyarrow`, `httpx`, `fastapi` | Transform and join tabular data, publish Parquet, retrieve Frankfurter exchange rates, and load the shared FX module. The current FX module defines its FastAPI application when imported, so `fastapi` is required by the batch FX command too. |
| Optional FX HTTP server | `uvicorn[standard]` | Serve the exchange-rate refresh endpoints when `trade-api-usd-exchange-rates --serve` is used. |
| Dashboard | `pandas`, `pyarrow`, `streamlit`, `plotly` | Read the Silver Parquet dataset and provide the interactive UI and charts. |

Packages in `python -m pip list` beyond this table are usually transitive dependencies. Preview what pip would install without changing the environment with:

```powershell
python -m pip install . --dry-run
```

On macOS or Linux, activate the environment with this command:

```bash
source .venv/bin/activate
```

You can also run the environment's Python executable without activation:

```powershell
# Windows
.\.venv\Scripts\python.exe -m pip install .

# macOS or Linux
.venv/bin/python -m pip install .
```

## How to use it: activate and run

A complete run consists of activating the environment, refreshing exchange rates, transforming the data, running the read-only quality check, and optionally starting the dashboard.

1. Open PowerShell in the repository root. If the intended virtual environment is not active, activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the project if it has not yet been installed in this environment:

   ```powershell
   python -m pip install .
   ```

3. Confirm that `data_pipeline/data/0_bronze/trades.xml` and `data_pipeline/data/0_bronze/securities.csv` exist.

4. Generate the required currency-rate input:

   ```powershell
   trade-api-usd-exchange-rates
   ```

5. Transform and enrich the Bronze inputs:

   ```powershell
   trade-transform
   ```

6. Check the published dataset without modifying it:

   ```powershell
   trade quality-checks
   ```

7. Start the dashboard after Silver has been published:

   ```powershell
   trade-dashboard
   ```

   Open <http://127.0.0.1:8501>. Press `Ctrl+C` in the terminal to stop the dashboard.

## How does it work?

The supplied Bronze inputs are stored in `data_pipeline/data/0_bronze/`. They include `trades.xml` and `securities.csv`; the exchange-rate command generates the third required Bronze input, `currencies.csv`.

`trade-api-usd-exchange-rates` reads every `tradeDate` in `trades.xml`, finds the earliest and latest UTC dates, and downloads the required daily USD exchange rates from Frankfurter for that inclusive range. After a successful refresh, it creates or replaces `data_pipeline/data/0_bronze/currencies.csv`. This file is needed because it provides the exchange rates and validity dates used to convert and enrich the trades.

`trade-transform` requires all three Bronze files: `trades.xml`, `securities.csv`, and the generated `currencies.csv`. It validates, transforms, and enriches the trades, then publishes the canonical enriched dataset as **`data_pipeline/data/1_silver/trades_enriched.parquet`**. If any required Bronze file is missing, the command exits with an error and does not publish a new Silver dataset.

The quality check and dashboard both read `trades_enriched.parquet`. The dashboard does not perform ingestion or transformation.

If `currencies.csv` already contains rates covering every source trade date, skip the network refresh and run:

```powershell
trade-transform
trade quality-checks
trade-dashboard
```

The supplied batch contains 300 trades for 15 January 2025.

Explicit `--start-date` and `--end-date` values override the dates inferred from the trades, so the caller must ensure that the chosen range covers the trades being transformed.

## Commands

| Command | Purpose |
| --- | --- |
| `trade-api-usd-exchange-rates` | Refresh the daily USD exchange rates for the source trade dates. |
| `trade-transform` | Read the Bronze inputs, transform and enrich the trades, and publish the Silver dataset. |
| `trade quality-checks` | Check the published Parquet file without changing it. |
| `trade-dashboard` | Start the dashboard at <http://127.0.0.1:8501>. |

Each command supports `--help`.

If the previous commands do not work, these are the equivalent Python module commands:

```powershell
python -m data_pipeline.fx_api
python -m data_pipeline.data_pipeline
python -m data_pipeline.quality_checks
python -m Dashboard.cli
```

Options work in the same way, such as `python -m data_pipeline.fx_api --start-date 2025-01-01 --end-date 2025-01-31`.

Use these commands for a complete run with refreshed exchange rates:

```powershell
trade-api-usd-exchange-rates
trade-transform
trade quality-checks
trade-dashboard
```

Examples with options:

```powershell
trade-api-usd-exchange-rates --start-date 2025-01-01 --end-date 2025-01-31
trade-api-usd-exchange-rates --serve
trade quality-checks C:\data\trades_enriched.parquet
trade-dashboard --port 8502 --trades-path C:\data\trades_enriched.parquet
```

The local API documentation is at <http://127.0.0.1:8000/docs>. Frankfurter is the only exchange-rate provider and does not require an API key. Quantities use nullable integers. Published Silver columns use uppercase data-type prefixes.

## Run the unit checks

After you install the project from the source checkout, run these component checks:

```powershell
trade-api-usd-exchange-rates --test
trade-transform --test
```

The exchange-rate suite tests mocked daily-rate ingestion and API endpoint functions. The transformation suite tests data cleanup, data types, enrichment, Silver column names, atomic Parquet publication, and failure handling.

Both suites use temporary fixtures and mocks. They do not call the live provider. They do not read or change the supplied datasets. A successful check returns exit code 0. A failed check returns a nonzero exit code.

Run the complete test suite and dependency check with these commands:

```powershell
python -m unittest discover -s tests -t . -v
python -m pip check
```

See [test responsibilities](tests/README.md) for the scope of each test group.

## Configure the data location

The datasets are external inputs and outputs. They are not package contents. In the source checkout, the commands use `data_pipeline/data/`.

For another location, set `DWS_DATA_ROOT` to the producer directory. This directory must contain `data/0_bronze/` and `data/1_silver/`:

```powershell
$env:DWS_DATA_ROOT = "C:\path\to\project\data_pipeline"
```

If `DWS_DATA_ROOT` is not set and no source checkout is available, the commands use the current working directory as the producer root.

`DWS_TRADES_PATH` overrides the dashboard's Parquet source. The `--trades-path` dashboard option provides the same override. Installing the package does not get or change any data.

## Project layout

| Path | Responsibility |
| --- | --- |
| `pyproject.toml` | Defines project metadata, the Python requirement, direct dependencies, and console commands. |
| `data_pipeline/` | Contains exchange-rate ingestion, processing stages, naming rules, and quality checks. |
| `Dashboard/` | Contains analytics, the Streamlit UI, and the dashboard command. |
| `tests/` | Contains checks grouped by pipeline stage and consumer. |

Dependency ranges are declared in one place. Pip resolves the transitive dependencies.

See [pipeline details](data_pipeline/README.md) and [dashboard details](Dashboard/README.md) for component-specific information.
