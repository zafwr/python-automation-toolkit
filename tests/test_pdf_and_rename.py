import os

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from autotool.pdftools import PdfError, extract_text, merge_pdfs, parse_page_ranges, split_pdf
from autotool.rename import RenameError, apply_renames, plan_renames, slugify


def make_pdf(path, pages):
    pdf = canvas.Canvas(str(path))
    for text in pages:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return path


def test_parse_page_ranges():
    assert parse_page_ranges("1-3, 5", 6) == [[0, 1, 2], [4]]
    with pytest.raises(PdfError):
        parse_page_ranges("4-9", 5)
    with pytest.raises(PdfError):
        parse_page_ranges("a-b", 5)


def test_merge_split_and_extract(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["Alpha one", "Alpha two"])
    b = make_pdf(tmp_path / "b.pdf", ["Beta one"])

    merged = tmp_path / "merged.pdf"
    assert merge_pdfs([a, b], merged) == 3
    assert "Beta one" in PdfReader(merged).pages[2].extract_text()

    pages = split_pdf(merged, tmp_path / "pages")
    assert [p.name for p in pages] == ["merged_p1.pdf", "merged_p2.pdf", "merged_p3.pdf"]

    ranges = split_pdf(merged, tmp_path / "ranges", "1-2,3")
    assert [len(PdfReader(p).pages) for p in ranges] == [2, 1]

    text = extract_text(merged)
    assert "--- Page 2 ---" in text and "Alpha two" in text


def test_slugify():
    assert slugify("Fatura Ocak 2026 (1)") == "fatura-ocak-2026-1"
    assert slugify("Şirket Raporu") == "sirket-raporu"


def test_rename_preview_then_apply(tmp_path):
    for name in ("Invoice B.pdf", "Invoice A.pdf", "notes.txt"):
        (tmp_path / name).write_text(name)

    plan = plan_renames(tmp_path, "{index:02}_{slug}{ext}", pattern="*.pdf")
    assert [(r.source.name, r.target.name) for r in plan] == [
        ("Invoice A.pdf", "01_invoice-a.pdf"),
        ("Invoice B.pdf", "02_invoice-b.pdf"),
    ]
    assert (tmp_path / "Invoice A.pdf").exists()  # planning changes nothing

    apply_renames(plan)
    assert sorted(os.listdir(tmp_path)) == ["01_invoice-a.pdf", "02_invoice-b.pdf", "notes.txt"]
    assert (tmp_path / "01_invoice-a.pdf").read_text() == "Invoice A.pdf"


def test_rename_handles_swaps(tmp_path):
    (tmp_path / "1.txt").write_text("one")
    (tmp_path / "2.txt").write_text("two")
    plan = plan_renames(tmp_path, "{index}.txt", start=0)  # 1->0, 2->1 (1.txt is also being renamed)
    apply_renames(plan)
    assert (tmp_path / "0.txt").read_text() == "one"
    assert (tmp_path / "1.txt").read_text() == "two"


def test_rename_refuses_duplicates_and_overwrites(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    with pytest.raises(RenameError, match="duplicate"):
        plan_renames(tmp_path, "same.txt")

    (tmp_path / "keep.md").write_text("keep")
    with pytest.raises(RenameError, match="overwrite"):
        plan_renames(tmp_path, "keep.md", pattern="a.txt")

    with pytest.raises(RenameError, match="invalid template"):
        plan_renames(tmp_path, "{nope}")
