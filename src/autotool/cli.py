"""Command-line interface: `autotool --help`."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .pdftools import PdfError, extract_text, merge_pdfs, split_pdf
from .rename import RenameError, apply_renames, plan_renames
from .report import summarize, write_report
from .tables import TableError, clean, merge_tables, read_table, write_table

app = typer.Typer(help="Everyday office automation: Excel/CSV, reports, PDFs and file renaming.", no_args_is_help=True)
pdf_app = typer.Typer(help="Merge, split and extract text from PDFs.", no_args_is_help=True)
app.add_typer(pdf_app, name="pdf")
console = Console()


def _fail(message: str) -> None:
    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code=1)


def _version(value: bool) -> None:
    if value:
        console.print(f"autotool {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show the version."),
) -> None:
    pass


# --- tables ---------------------------------------------------------------


@app.command()
def merge(
    inputs: list[Path] = typer.Argument(..., help="CSV/Excel files to combine."),
    output: Path = typer.Option(..., "--output", "-o", help="Output .csv or .xlsx file."),
    no_source: bool = typer.Option(False, "--no-source", help="Don't add a source_file column."),
    clean_data: bool = typer.Option(True, "--clean/--no-clean", help="Trim text, drop empty rows and duplicates."),
) -> None:
    """Combine several CSV/Excel files with similar columns into one table."""
    try:
        df = merge_tables(inputs, source_column=None if no_source else "source_file")
        before = len(df)
        if clean_data:
            df = clean(df, normalize_headers=False)
        write_table(df, output)
    except TableError as error:
        _fail(str(error))
    console.print(
        f"[green]✓[/green] Merged {len(inputs)} files → {output} "
        f"({len(df)} rows, {before - len(df)} empty/duplicate rows removed)"
    )


@app.command("clean")
def clean_command(
    input: Path = typer.Argument(..., help="CSV/Excel file to clean."),
    output: Path = typer.Option(..., "--output", "-o", help="Output .csv or .xlsx file."),
    keep_headers: bool = typer.Option(False, "--keep-headers", help="Don't rename headers to snake_case."),
    keep_duplicates: bool = typer.Option(False, "--keep-duplicates", help="Don't remove duplicate rows."),
) -> None:
    """Tidy a messy export: snake_case headers, trimmed text, no empty or duplicate rows."""
    try:
        df = read_table(input)
        cleaned = clean(df, normalize_headers=not keep_headers, drop_duplicates=not keep_duplicates)
        write_table(cleaned, output)
    except TableError as error:
        _fail(str(error))
    console.print(f"[green]✓[/green] {input.name}: {len(df)} → {len(cleaned)} rows, saved to {output}")


@app.command()
def report(
    input: Path = typer.Argument(..., help="CSV/Excel file with the data."),
    group_by: str = typer.Option(..., "--by", help="Column to group by (e.g. region)."),
    value: str = typer.Option(..., "--value", help="Column to aggregate (e.g. amount)."),
    agg: str = typer.Option("sum", "--agg", help="sum, mean, count, min or max."),
    output: Path = typer.Option(..., "--output", "-o", help="Output .xlsx report."),
) -> None:
    """Create an Excel report with a summary sheet, totals row and bar chart."""
    try:
        df = clean(read_table(input))
        summary = summarize(df, group_by, value, agg)
        write_report(df, summary, output, title=f"{value} by {group_by}")
    except TableError as error:
        _fail(str(error))

    table = Table(title=f"{agg} of {value} by {group_by}")
    for column in summary.columns:
        table.add_column(str(column))
    for row in summary.head(10).itertuples(index=False):
        table.add_row(*(f"{v:,.2f}" if isinstance(v, float) else str(v) for v in row))
    console.print(table)
    console.print(f"[green]✓[/green] Report saved to {output}")


# --- pdf ------------------------------------------------------------------


@pdf_app.command("merge")
def pdf_merge(
    inputs: list[Path] = typer.Argument(..., help="PDFs in the order they should appear."),
    output: Path = typer.Option(..., "--output", "-o"),
) -> None:
    """Merge PDFs into a single file."""
    try:
        pages = merge_pdfs(inputs, output)
    except (PdfError, FileNotFoundError) as error:
        _fail(str(error))
    console.print(f"[green]✓[/green] {len(inputs)} files → {output} ({pages} pages)")


@pdf_app.command("split")
def pdf_split(
    input: Path = typer.Argument(...),
    output_dir: Path = typer.Option(Path("split"), "--output-dir", "-d"),
    ranges: str = typer.Option(None, "--ranges", "-r", help="e.g. '1-3,4,5-8'. Default: one file per page."),
) -> None:
    """Split a PDF into single pages or page ranges."""
    try:
        files = split_pdf(input, output_dir, ranges)
    except (PdfError, FileNotFoundError) as error:
        _fail(str(error))
    console.print(f"[green]✓[/green] Wrote {len(files)} files to {output_dir}/")


@pdf_app.command("text")
def pdf_text(
    input: Path = typer.Argument(...),
    output: Path = typer.Option(None, "--output", "-o", help="Save to a .txt file instead of printing."),
) -> None:
    """Extract the text of every page."""
    try:
        text = extract_text(input)
    except FileNotFoundError as error:
        _fail(str(error))
    if output:
        output.write_text(text, encoding="utf-8")
        console.print(f"[green]✓[/green] Text saved to {output}")
    else:
        console.print(text, markup=False, highlight=False)


# --- rename ---------------------------------------------------------------


@app.command()
def rename(
    directory: Path = typer.Argument(..., help="Folder with the files."),
    template: str = typer.Option(..., "--template", "-t", help="e.g. '{date}_{index:03}_{slug}{ext}'"),
    pattern: str = typer.Option("*", "--pattern", "-p", help="Only files matching this glob, e.g. '*.pdf'."),
    start: int = typer.Option(1, "--start", help="First number for {index}."),
    apply: bool = typer.Option(False, "--apply", help="Actually rename. Without it, only a preview is shown."),
) -> None:
    """Bulk-rename files from a template. Shows a preview unless --apply is given."""
    try:
        plan = plan_renames(directory, template, pattern=pattern, start=start)
    except RenameError as error:
        _fail(str(error))
    if not plan:
        console.print("Nothing to rename.")
        return

    table = Table(title="Rename plan" + ("" if apply else " (preview)"))
    table.add_column("Current name")
    table.add_column("New name", style="green")
    for item in plan:
        table.add_row(item.source.name, item.target.name)
    console.print(table)

    if apply:
        apply_renames(plan)
        console.print(f"[green]✓[/green] Renamed {len(plan)} files.")
    else:
        console.print("[yellow]Preview only.[/yellow] Run again with --apply to rename.")


if __name__ == "__main__":
    app()
