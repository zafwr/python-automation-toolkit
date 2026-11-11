from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from autotool.cli import app

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and "autotool" in result.output


def test_merge_command_cleans_and_writes_excel(tmp_path):
    output = tmp_path / "all.xlsx"
    result = runner.invoke(
        app, ["merge", str(EXAMPLES / "sales_january.csv"), str(EXAMPLES / "sales_february.csv"), "-o", str(output)]
    )
    assert result.exit_code == 0, result.output
    df = pd.read_excel(output)
    # 6 January rows minus 1 duplicate and 1 empty row = 5, plus 5 February rows.
    assert len(df) == 10
    assert "Izmir" in set(df["region"])  # "  Izmir " was trimmed


def test_report_command(tmp_path):
    merged = tmp_path / "all.csv"
    runner.invoke(app, ["merge", str(EXAMPLES / "sales_january.csv"), str(EXAMPLES / "sales_february.csv"), "-o", str(merged)])
    output = tmp_path / "report.xlsx"
    result = runner.invoke(app, ["report", str(merged), "--by", "region", "--value", "amount", "-o", str(output)])
    assert result.exit_code == 0, result.output
    summary = pd.read_excel(output, sheet_name="Summary")
    assert summary.iloc[0]["region"] == "Istanbul"
    assert summary.iloc[-1]["region"] == "TOTAL"


def test_report_with_bad_column_shows_error(tmp_path):
    result = runner.invoke(
        app, ["report", str(EXAMPLES / "sales_february.csv"), "--by", "city", "--value", "amount", "-o", str(tmp_path / "r.xlsx")]
    )
    assert result.exit_code == 1
    assert "not found" in result.output


def test_rename_preview_does_not_touch_files(tmp_path):
    (tmp_path / "My File.txt").write_text("x")
    result = runner.invoke(app, ["rename", str(tmp_path), "-t", "{slug}{ext}"])
    assert result.exit_code == 0
    assert "Preview only" in result.output
    assert (tmp_path / "My File.txt").exists()

    result = runner.invoke(app, ["rename", str(tmp_path), "-t", "{slug}{ext}", "--apply"])
    assert result.exit_code == 0
    assert (tmp_path / "my-file.txt").exists()
