"""Read, clean and merge CSV / Excel tables."""

import re
import unicodedata
from pathlib import Path

import pandas as pd

TABLE_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class TableError(ValueError):
    pass


def read_table(path: Path) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame (first sheet for Excel)."""
    suffix = path.suffix.lower()
    if suffix not in TABLE_EXTENSIONS:
        raise TableError(f"{path.name}: unsupported file type (use .csv, .xlsx or .xls)")
    if not path.exists():
        raise TableError(f"{path}: file not found")
    if suffix == ".csv":
        # sep=None lets pandas detect commas, semicolons (common in Turkish/European exports) or tabs.
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    return pd.read_excel(path)


def write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")  # BOM so Excel shows accents correctly
    elif path.suffix.lower() == ".xlsx":
        df.to_excel(path, index=False)
    else:
        raise TableError(f"{path.name}: output must be .csv or .xlsx")


def normalize_header(name: object) -> str:
    """'  Customer Name ' -> 'customer_name', 'Şehir' -> 'sehir'."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    return text or "column"


def _dedupe_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for name in names:
        if name in seen:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 0
            result.append(name)
    return result


def clean(
    df: pd.DataFrame,
    *,
    normalize_headers: bool = True,
    strip_text: bool = True,
    drop_empty_rows: bool = True,
    drop_duplicates: bool = True,
) -> pd.DataFrame:
    """Apply the common cleanup steps that most messy exports need."""
    out = df.copy()
    if normalize_headers:
        out.columns = _dedupe_names([normalize_header(c) for c in out.columns])
    if strip_text:
        for column in out.columns:
            if pd.api.types.is_string_dtype(out[column]) or out[column].dtype == object:
                out[column] = out[column].map(lambda v: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v)
                out[column] = out[column].replace("", pd.NA)
    if drop_empty_rows:
        out = out.dropna(how="all")
    if drop_duplicates:
        out = out.drop_duplicates()
    return out.reset_index(drop=True)


def merge_tables(paths: list[Path], *, source_column: str | None = "source_file") -> pd.DataFrame:
    """Stack several tables into one. Columns are matched by normalized header name.

    Missing columns in a file are left empty, so files with slightly different
    layouts can still be combined.
    """
    if not paths:
        raise TableError("no input files given")
    frames = []
    for path in paths:
        frame = read_table(path)
        frame.columns = _dedupe_names([normalize_header(c) for c in frame.columns])
        # Drop blank rows now; once the source column is added they would no longer look empty.
        frame = frame.dropna(how="all")
        if source_column:
            frame.insert(0, source_column, path.name)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)
