"""Installed command for launching the packaged Streamlit dashboard."""
import argparse
from importlib.resources import files
import os
from pathlib import Path
import subprocess
import sys
import tomllib


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the DWS trade analytics dashboard")
    parser.add_argument("--port", type=int, default=8501, help="HTTP port (default: 8501)")
    parser.add_argument("--host", default="127.0.0.1", help="Listening address (default: 127.0.0.1)")
    parser.add_argument("--trades-path", type=Path, help="Read an explicit enriched Parquet dataset")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    package = files("Dashboard")
    command = [
        sys.executable, "-m", "streamlit", "run", str(package.joinpath("streamlit_app.py")),
        f"--server.address={args.host}", f"--server.port={args.port}",
        "--server.headless=true", "--browser.gatherUsageStats=false",
    ]
    theme = tomllib.loads(package.joinpath(".streamlit/config.toml").read_text(encoding="utf-8"))["theme"]
    command.extend(f"--theme.{key}={value}" for key, value in theme.items())
    environment = os.environ.copy()
    if args.trades_path:
        environment["DWS_TRADES_PATH"] = str(args.trades_path.expanduser().resolve())
    if not environment.get("DWS_DATA_ROOT"):
        source_root = Path(__file__).resolve().parents[1] / "data_pipeline"
        checkout_root = Path.cwd() / "data_pipeline"
        root = next((path for path in (source_root, checkout_root) if (path / "data").is_dir()), Path.cwd())
        environment["DWS_DATA_ROOT"] = str(root.resolve())
    try:
        result = subprocess.run(command, env=environment)
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
