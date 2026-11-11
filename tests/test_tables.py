from pathlib import Path

import pandas as pd
import pytest

from autotool.report import summarize, write_report
from autotool.tables import TableError, clean, merge_tables, normalize_header, read_table, write_table

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_normalize_header_handles_spaces_case_and_turkish_letters():
    assert normalize_header("  Customer Name ") == "customer_name"
    assert normalize_header("Şehir / İlçe") == "sehir_ilce"
    assert normalize_header("%%") == "column"


def test_clean_trims_text_and_drops_empty_and_duplicate_rows():
    df = pd.DataFrame({" Name ": ["  Ali ", "Ali", None, "Ayşe  Kaya"], "Score": [1, 1, None, 2]})
    out = clean(df)
    assert list(out.columns) == ["name", "score"]
    assert list(out["name"]) == ["Ali", "Ayşe Kaya"]


def test_read_csv_detects_semicolon_separator():
    df = read_table(EXAMPLES / "sales_february.csv")
    assert list(df.columns) == ["Order ID", "Region", "Product", "Amount", "Sales Rep"]
    assert len(df) == 5


def test_merge_aligns_columns_and_adds_source():
    df = merge_tables([EXAMPLES / "sales_january.csv", EXAMPLES / "sales_february.csv"])
    assert {"source_file", "order_id", "region", "amount", "sales_rep"} <= set(df.columns)
    assert set(df["source_file"]) == {"sales_january.csv", "sales_february.csv"}
    # January has no sales rep column, so those rows are empty there.
    assert df.loc[df["source_file"] == "sales_january.csv", "sales_rep"].isna().all()


def test_write_and_read_round_trip(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "ş"]})
    for name in ("out.csv", "out.xlsx"):
        write_table(df, tmp_path / name)
        assert read_table(tmp_path / name).equals(read_table(tmp_path / name))
        assert list(read_table(tmp_path / name)["b"]) == ["x", "ş"]


def test_unsupported_and_missing_files_raise():
    with pytest.raises(TableError):
        read_table(Path("notes.txt"))
    with pytest.raises(TableError):
        read_table(Path("missing.csv"))


def test_summarize_groups_and_sorts():
    df = pd.DataFrame({"region": ["A", "B", "A"], "amount": ["10", "5", "7"]})
    summary = summarize(df, "region", "amount", "sum")
    assert summary.to_dict("records") == [{"region": "A", "amount_sum": 17}, {"region": "B", "amount_sum": 5}]


def test_summarize_rejects_unknown_column():
    with pytest.raises(TableError, match="not found"):
        summarize(pd.DataFrame({"a": [1]}), "region", "a")


def test_report_has_summary_total_and_chart(tmp_path):
    from openpyxl import load_workbook

    df = pd.DataFrame({"region": ["A", "B", "A"], "amount": [10, 5, 7]})
    path = tmp_path / "report.xlsx"
    write_report(df, summarize(df, "region", "amount"), path)

    workbook = load_workbook(path)
    assert workbook.sheetnames == ["Summary", "Data"]
    sheet = workbook["Summary"]
    assert [c.value for c in sheet[sheet.max_row]] == ["TOTAL", 22]
    assert len(sheet._charts) == 1
