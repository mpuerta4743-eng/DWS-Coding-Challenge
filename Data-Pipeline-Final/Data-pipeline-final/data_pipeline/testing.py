"""Run isolated unit suites from the source checkout without supplied datasets."""
from pathlib import Path
import subprocess
import sys
import tomllib


UNIT_AREAS = {
    "api-usd-exchange-rates": ("ingestion",),
    "transform": ("transformation", "enrichment", "semantics", "publication"),
}


def find_checkout() -> Path:
    candidates = (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents)
    for candidate in candidates:
        metadata = candidate / "pyproject.toml"
        if not metadata.is_file() or not (candidate / "tests/pipeline").is_dir():
            continue
        project = tomllib.loads(metadata.read_text(encoding="utf-8")).get("project", {})
        if project.get("name") == "dws-trade-analytics":
            return candidate
    raise SystemExit("Unit checks require the source checkout. Run this command from the project repository.")


def run_unit_checks(component: str) -> int:
    root = find_checkout()
    modules = [
        ".".join(path.relative_to(root).with_suffix("").parts)
        for area in UNIT_AREAS[component]
        for path in sorted((root / "tests/pipeline" / area).rglob("test_*.py"))
    ]
    if not modules:
        raise SystemExit(f"No unit checks found for {component}")
    # Explicit suites exclude live connectivity and checks against published data.
    return subprocess.run([sys.executable, "-m", "unittest", "-v", *modules], cwd=root).returncode
