"""Table-independent datatype prefixes for published Silver columns."""

from __future__ import annotations

import pandas as pd
from pandas.api import types as ptypes


# One naming dictionary shared by every Silver table, independent of business fields.
SILVER_DATATYPE_PREFIXES = {
    "integer": "INT",
    "floating": "FLOAT",
    "string": "STRING",
    "boolean": "BOOLEAN",
    "datetime": "TIMESTAMP",
    "timedelta": "DURATION",
}


def column_datatype(column: pd.Series) -> str:
    """Classify actual pandas dtypes; never guess a type from a column name."""
    dtype = column.dtype
    if ptypes.is_bool_dtype(dtype):
        return "boolean"
    if ptypes.is_integer_dtype(dtype):
        return "integer"
    if ptypes.is_float_dtype(dtype):
        return "floating"
    if ptypes.is_datetime64_any_dtype(dtype):
        return "datetime"
    if ptypes.is_timedelta64_dtype(dtype):
        return "timedelta"
    if isinstance(dtype, pd.StringDtype):
        return "string"
    # CSV-derived strings can have object dtype. Mixed or ambiguous objects must
    # be explicitly typed before entering Silver, including all-null object columns.
    if ptypes.is_object_dtype(dtype):
        values = column.dropna()
        if not values.empty and values.map(lambda value: isinstance(value, str)).all():
            return "string"
    raise TypeError(
        f"Column {column.name!r} has unsupported or ambiguous dtype {dtype}; "
        "assign an explicit supported dtype before publishing Silver"
    )


def silver_column_mapping(frame: pd.DataFrame) -> dict[str, str]:
    """Build a source -> Silver naming dictionary for any typed table."""
    if not frame.columns.is_unique:
        raise ValueError("Silver tables must have unique column names")
    mapping = {}
    prefixes = tuple(f"{prefix}_" for prefix in SILVER_DATATYPE_PREFIXES.values())
    for name in frame.columns:
        if not isinstance(name, str) or not name:
            raise ValueError("Silver column names must be nonempty strings")
        prefix = SILVER_DATATYPE_PREFIXES[column_datatype(frame[name])] + "_"
        normalized_name = name.strip().upper()
        if not normalized_name:
            raise ValueError("Silver column names must be nonempty strings")
        if normalized_name.startswith(prefix):
            mapping[name] = normalized_name
        elif normalized_name.startswith(prefixes):
            raise ValueError(f"Column {name!r} does not match its datatype prefix {prefix!r}")
        else:
            mapping[name] = prefix + normalized_name
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Datatype prefixes produce duplicate Silver column names")
    return mapping


def semanticize_silver(frame: pd.DataFrame) -> pd.DataFrame:
    """Uppercase and prefix names without changing data or the input."""
    return frame.rename(columns=silver_column_mapping(frame)).copy()


def validate_silver_names(frame: pd.DataFrame) -> None:
    """Reject unsemanticized columns at the publication boundary."""
    mapping = silver_column_mapping(frame)
    if any(source != target for source, target in mapping.items()):
        raise ValueError("Apply semanticize_silver before publishing a Silver table")
