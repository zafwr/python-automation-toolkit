"""Merge, split and extract text from PDF files."""

from pathlib import Path

from pypdf import PdfReader, PdfWriter


class PdfError(ValueError):
    pass


def parse_page_ranges(spec: str, page_count: int) -> list[list[int]]:
    """'1-3,5,7-8' -> [[0,1,2],[4],[6,7]] (0-based page indexes)."""
    groups = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start, end = int(start_text), int(end_text)
            else:
                start = end = int(part)
        except ValueError as error:
            raise PdfError(f"invalid page range '{part}'") from error
        if not 1 <= start <= end <= page_count:
            raise PdfError(f"page range '{part}' is outside 1-{page_count}")
        groups.append(list(range(start - 1, end)))
    if not groups:
        raise PdfError("no page ranges given")
    return groups


def merge_pdfs(inputs: list[Path], output: Path) -> int:
    """Merge PDFs in the given order. Returns the total page count."""
    if not inputs:
        raise PdfError("no input files given")
    writer = PdfWriter()
    for path in inputs:
        for page in PdfReader(path).pages:
            writer.add_page(page)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)
    return len(writer.pages)


def split_pdf(input_path: Path, output_dir: Path, ranges: str | None = None) -> list[Path]:
    """Split a PDF into one file per page, or one file per range ('1-3,4-6')."""
    reader = PdfReader(input_path)
    page_count = len(reader.pages)
    groups = parse_page_ranges(ranges, page_count) if ranges else [[i] for i in range(page_count)]

    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for group in groups:
        writer = PdfWriter()
        for index in group:
            writer.add_page(reader.pages[index])
        label = f"p{group[0] + 1}" if len(group) == 1 else f"p{group[0] + 1}-{group[-1] + 1}"
        path = output_dir / f"{input_path.stem}_{label}.pdf"
        with path.open("wb") as handle:
            writer.write(handle)
        written.append(path)
    return written


def extract_text(input_path: Path) -> str:
    """Return the text of every page, separated by page markers."""
    reader = PdfReader(input_path)
    parts = [f"--- Page {i} ---\n{(page.extract_text() or '').strip()}" for i, page in enumerate(reader.pages, start=1)]
    return "\n\n".join(parts)
