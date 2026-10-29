# Test map

Run component unit checks from the repository root:

```powershell
trade-api-usd-exchange-rates --test
trade-transform --test
```

The first selects pipeline/ingestion, including mocked API endpoint-function checks. The second selects pipeline/transformation, pipeline/enrichment, pipeline/semantics and pipeline/publication. Both exclude dashboard, live connectivity and actual published-data checks. Exit code 0 means success; nonzero means failure. The source checkout is required, but no additional dependency installation is needed.

Run all tests from the repository root:

```powershell
python -m unittest discover -s tests -t . -v
```

| Folder | Pipeline reference | Why these tests exist |
| --- | --- | --- |
| pipeline/ingestion | Frankfurter to Bronze | Mocked references, inferred trade dates, current-security currency discovery and precision |
| pipeline/orchestration | Installed component commands | Verify command entry points and data-root behavior |
| pipeline/transformation | Bronze cleanup and local values | Preserve types/nulls, enforce integer quantities and normalize text |
| pipeline/enrichment | Reference joins and USD values | Preserve trade rows, security flags and time-valid FX selection |
| pipeline/semantics | Enriched data to published names | Validate datatype prefixes, uppercase collisions and generic tables |
| pipeline/publication | Silver file | Typed Parquet round trips and atomic failure handling |
| pipeline/quality | Quality checker with temporary files | Verify valid/invalid reports without changing persisted data |
| dashboard/analytics | Silver consumption | Source overrides, flagged counts and missing USD aggregation |
| dashboard | Installed dashboard launcher | Verify options, invalid ports and server exit codes |
| dashboard/ui | Streamlit presentation | Rankings, filters, search and empty results |
| integration | Live Frankfurter connectivity | Opt-in read-only provider response check |
| published_data | Supplied Silver Parquet | Read-only security coverage, ID uniqueness and BUY/SELL quality gates |

The pipeline and dashboard suites use temporary datasets and mocked provider responses. The published_data suite deliberately reads the actual existing Silver file and fails if it is absent or invalid; it never repairs data. It is included in full discovery. Live connectivity is skipped unless explicitly enabled.

```powershell
# Isolated pipeline and dashboard checks:
python -m unittest discover -s tests/pipeline -t . -v
python -m unittest discover -s tests/dashboard -t . -v
# Actual published-data checks:
python -m unittest discover -s tests/published_data -t . -v
# Read-only live provider check:
$env:RUN_FX_CONNECTIVITY_TESTS = "1"
try {
    python -m unittest tests.integration.test_frankfurter_connectivity -v
} finally {
    Remove-Item Env:RUN_FX_CONNECTIVITY_TESTS
}
```

Keep `-t .` for discovery so the root test package resolves both component source directories.
