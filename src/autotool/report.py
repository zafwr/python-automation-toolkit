"""Build a formatted Excel summary report from a table."""

from pathlib import Path

import pandas as pd
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .tables import TableError

AGGREGATIONS = {"sum", "mean", "count", "min", "max"}
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
TOTAL_FILL = PatternFill("solid", fgColor="DDEBF7")


def summarize(df: pd.DataFrame, group_by: str, value: str, agg: str = "sum") -> pd.DataFrame:
    """Group rows by one column and aggregate another, sorted from largest to smallest."""
    for column in (group_by, value):
        if column not in df.columns:
            raise TableError(f"column '{column}' not found. Available: {', '.join(map(str, df.columns))}")
    if agg not in AGGREGATIONS:
        raise TableError(f"aggregation must be one of: {', '.join(sorted(AGGREGATIONS))}")

    values = pd.to_numeric(df[value], errors="coerce") if agg != "count" else df[value]
    summary = (
        pd.DataFrame({group_by: df[group_by], value: values})
        .groupby(group_by, dropna=False)[value]
        .agg(agg)
        .reset_index()
        .rename(columns={value: f"{value}_{agg}"})
        .sort_values(f"{value}_{agg}", ascending=False, ignore_index=True)
    )
    return summary


def _style_sheet(worksheet, total_row: bool) -> None:
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
    if total_row:
        for cell in worksheet[worksheet.max_row]:
            cell.font = Font(bold=True)
            cell.fill = TOTAL_FILL
    worksheet.freeze_panes = "A2"
    for index, column in enumerate(worksheet.columns, start=1):
        width = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column)
        worksheet.column_dimensions[get_column_letter(index)].width = min(max(width + 2, 10), 50)


def write_report(data: pd.DataFrame, summary: pd.DataFrame, path: Path, title: str = "Summary") -> None:
    """Write a two-sheet workbook: a summary with totals and a bar chart, plus the raw data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    value_column = summary.columns[1]
    with_total = pd.concat(
        [summary, pd.DataFrame({summary.columns[0]: ["TOTAL"], value_column: [summary[value_column].sum()]})],
        ignore_index=True,
    )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        with_total.to_excel(writer, sheet_name="Summary", index=False)
        data.to_excel(writer, sheet_name="Data", index=False)

        summary_sheet = writer.sheets["Summary"]
        _style_sheet(summary_sheet, total_row=True)
        _style_sheet(writer.sheets["Data"], total_row=False)

        for row in summary_sheet.iter_rows(min_row=2, min_col=2, max_col=2):
            for cell in row:
                cell.number_format = "#,##0.##"

        if len(summary) > 0:
            chart = BarChart()
            chart.title = title
            chart.legend = None
            chart.y_axis.title = value_column
            last_row = len(summary) + 1  # exclude the TOTAL row from the chart
            chart.add_data(Reference(summary_sheet, min_col=2, min_row=1, max_row=last_row), titles_from_data=True)
            chart.set_categories(Reference(summary_sheet, min_col=1, min_row=2, max_row=last_row))
            chart.height, chart.width = 8, 16
            summary_sheet.add_chart(chart, "D2")

        # Print the summary on one landscape page.
        summary_sheet.page_setup.orientation = "landscape"
        summary_sheet.page_setup.fitToWidth = 1
        summary_sheet.page_setup.fitToHeight = 1
        summary_sheet.sheet_properties.pageSetUpPr.fitToPage = True
