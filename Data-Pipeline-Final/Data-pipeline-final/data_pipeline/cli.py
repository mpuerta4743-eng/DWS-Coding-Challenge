"""Trade maintenance commands."""
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Trade maintenance commands")
    subcommands = parser.add_subparsers(dest="command", required=True)
    quality = subcommands.add_parser("quality-checks", help="Check published Parquet without modifying it")
    quality.add_argument("path", nargs="?", type=Path, help="Optional enriched Parquet path")
    args = parser.parse_args()
    from .quality_checks import main as quality_main
    quality_main([str(args.path)] if args.path else [])


if __name__ == "__main__":
    main()
