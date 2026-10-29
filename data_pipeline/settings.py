"""Resolve external dataset locations for source and installed execution."""
import os
from pathlib import Path


def data_root() -> Path:
    """Return the producer directory containing data/0_bronze and data/1_silver."""
    configured = os.environ.get("DWS_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    source_root = Path(__file__).resolve().parent
    if (source_root / "data").is_dir():
        return source_root
    checkout_root = Path.cwd() / "data_pipeline"
    if (checkout_root / "data").is_dir():
        return checkout_root.resolve()
    return Path.cwd().resolve()
