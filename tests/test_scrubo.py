"""
Unit tests for scrubo.py

Each test creates real in-memory PDFs via PyMuPDF so no fixture files are needed.
After redaction, the output PDF is re-opened and its text content is inspected to
confirm that sensitive terms were truly removed (not just visually covered).
"""

import re
import sys
import textwrap
from io import StringIO
from pathlib import Path

import pymupdf as fitz
import pytest

# Make the project root importable regardless of how pytest is invoked.
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrubo import (
    collect_input_files,
    find_rects_for_exact,
    find_rects_for_regex,
    load_rules,
    process_file,
    redact_pdf,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pdf(tmp_path: Path, name: str, pages: list[str]) -> Path:
    """Create a text-based PDF with one text block per page."""
    pdf_path = tmp_path / name
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def extract_text(pdf_path: Path) -> str:
    """Return all text from all pages of a PDF."""
    doc = fitz.open(str(pdf_path))
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


# ---------------------------------------------------------------------------
# load_rules
# ---------------------------------------------------------------------------

class TestLoadRules:
    def test_exact_rules(self, tmp_path):
        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("John Doe\nJane Smith\n", encoding="utf-8")
        rules = load_rules(str(rules_file))
        assert rules == [("exact", "John Doe"), ("exact", "Jane Smith")]

    def test_regex_rules(self, tmp_path):
        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("regex:\\d{4}-\\d{4}\n", encoding="utf-8")
        rules = load_rules(str(rules_file))
        assert rules == [("regex", "\\d{4}-\\d{4}")]

    def test_mixed_rules(self, tmp_path):
        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("John Doe\nregex:\\d{3}\nJane\n", encoding="utf-8")
        rules = load_rules(str(rules_file))
        assert rules == [
            ("exact", "John Doe"),
            ("regex", "\\d{3}"),
            ("exact", "Jane"),
        ]

    def test_comments_and_blank_lines_ignored(self, tmp_path):
        rules_file = tmp_path / "rules.txt"
        rules_file.write_text(
            textwrap.dedent("""\
            # This is a comment
            John Doe

            # Another comment
            Jane Smith
            """),
            encoding="utf-8",
        )
        rules = load_rules(str(rules_file))
        assert rules == [("exact", "John Doe"), ("exact", "Jane Smith")]

    def test_empty_file(self, tmp_path):
        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("# only comments\n\n", encoding="utf-8")
        rules = load_rules(str(rules_file))
        assert rules == []


# ---------------------------------------------------------------------------
# find_rects_for_exact
# ---------------------------------------------------------------------------

class TestFindRectsForExact:
    def _page_with_text(self, text: str) -> fitz.Page:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
        return page

    def test_finds_present_term(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["Hello John Doe welcome"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        rects = find_rects_for_exact(page, "John Doe", case_sensitive=False)
        doc.close()
        assert len(rects) >= 1

    def test_returns_empty_for_absent_term(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["Hello World"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        rects = find_rects_for_exact(page, "Jane Smith", case_sensitive=False)
        doc.close()
        assert rects == []

    def test_case_insensitive_match(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["JOHN DOE is here"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        rects = find_rects_for_exact(page, "john doe", case_sensitive=False)
        doc.close()
        assert len(rects) >= 1

    def test_case_sensitive_no_match(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["JOHN DOE is here"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        rects = find_rects_for_exact(page, "john doe", case_sensitive=True)
        doc.close()
        assert rects == []

    def test_case_sensitive_exact_match(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["John Doe is here"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        rects = find_rects_for_exact(page, "John Doe", case_sensitive=True)
        doc.close()
        assert len(rects) >= 1


# ---------------------------------------------------------------------------
# find_rects_for_regex
# ---------------------------------------------------------------------------

class TestFindRectsForRegex:
    def test_finds_regex_match(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["Card: 1234-5678-9012-3456"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        rects = find_rects_for_regex(page, r"\d{4}-\d{4}-\d{4}-\d{4}", case_sensitive=False)
        doc.close()
        assert len(rects) >= 1

    def test_returns_empty_when_no_match(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["No numbers here"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        rects = find_rects_for_regex(page, r"\d{4}-\d{4}", case_sensitive=False)
        doc.close()
        assert rects == []

    def test_regex_case_insensitive(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["Email: USER@EXAMPLE.COM"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        pattern = r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}"
        rects = find_rects_for_regex(page, pattern, case_sensitive=False)
        doc.close()
        assert len(rects) >= 1

    def test_regex_case_sensitive_no_match(self, tmp_path):
        pdf = make_pdf(tmp_path, "test.pdf", ["Email: USER@EXAMPLE.COM"])
        doc = fitz.open(str(pdf))
        page = doc[0]
        pattern = r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}"
        rects = find_rects_for_regex(page, pattern, case_sensitive=True)
        doc.close()
        assert rects == []


# ---------------------------------------------------------------------------
# redact_pdf — true removal
# ---------------------------------------------------------------------------

class TestRedactPdf:
    def test_exact_term_is_removed(self, tmp_path):
        src = make_pdf(tmp_path, "src.pdf", ["Account holder: John Doe\nBalance: $5,000"])
        out = tmp_path / "out.pdf"
        redact_pdf(str(src), [("exact", "John Doe")], str(out), case_sensitive=False, verbose=False)
        assert "John Doe" not in extract_text(out)
        assert "john doe" not in extract_text(out).lower()

    def test_non_targeted_text_is_preserved(self, tmp_path):
        src = make_pdf(tmp_path, "src.pdf", ["Name: John Doe\nBalance: $5,000"])
        out = tmp_path / "out.pdf"
        redact_pdf(str(src), [("exact", "John Doe")], str(out), case_sensitive=False, verbose=False)
        assert "$5,000" in extract_text(out)

    def test_regex_term_is_removed(self, tmp_path):
        src = make_pdf(tmp_path, "src.pdf", ["Card: 1234-5678-9012-3456\nAmount: $100"])
        out = tmp_path / "out.pdf"
        redact_pdf(
            str(src),
            [("regex", r"\d{4}-\d{4}-\d{4}-\d{4}")],
            str(out),
            case_sensitive=False,
            verbose=False,
        )
        assert "1234-5678-9012-3456" not in extract_text(out)

    def test_multiple_rules_applied(self, tmp_path):
        src = make_pdf(tmp_path, "src.pdf", ["Name: John Doe\nSSN: 123-45-6789"])
        out = tmp_path / "out.pdf"
        rules = [("exact", "John Doe"), ("regex", r"\d{3}-\d{2}-\d{4}")]
        redact_pdf(str(src), rules, str(out), case_sensitive=False, verbose=False)
        text = extract_text(out)
        assert "John Doe" not in text
        assert "123-45-6789" not in text

    def test_match_counts_returned(self, tmp_path):
        src = make_pdf(tmp_path, "src.pdf", ["John Doe\nJohn Doe again"])
        out = tmp_path / "out.pdf"
        counts = redact_pdf(
            str(src), [("exact", "John Doe")], str(out), case_sensitive=False, verbose=False
        )
        assert counts.get("John Doe", 0) >= 2

    def test_unmatched_rule_not_in_counts(self, tmp_path):
        src = make_pdf(tmp_path, "src.pdf", ["Hello World"])
        out = tmp_path / "out.pdf"
        counts = redact_pdf(
            str(src), [("exact", "Jane Smith")], str(out), case_sensitive=False, verbose=False
        )
        assert "Jane Smith" not in counts

    def test_multipage_redaction(self, tmp_path):
        src = make_pdf(
            tmp_path,
            "src.pdf",
            ["Page 1: John Doe", "Page 2: John Doe again", "Page 3: safe content"],
        )
        out = tmp_path / "out.pdf"
        redact_pdf(str(src), [("exact", "John Doe")], str(out), case_sensitive=False, verbose=False)
        text = extract_text(out)
        assert "John Doe" not in text
        assert "safe content" in text

    def test_case_sensitive_leaves_wrong_case(self, tmp_path):
        src = make_pdf(tmp_path, "src.pdf", ["JOHN DOE balance"])
        out = tmp_path / "out.pdf"
        redact_pdf(
            str(src), [("exact", "john doe")], str(out), case_sensitive=True, verbose=False
        )
        # Case-sensitive search for lowercase should NOT remove the uppercase version.
        assert "JOHN DOE" in extract_text(out)


# ---------------------------------------------------------------------------
# process_file — output path and summary
# ---------------------------------------------------------------------------

class TestProcessFile:
    def test_output_file_created_alongside_source(self, tmp_path):
        src = make_pdf(tmp_path, "statement.pdf", ["Name: John Doe"])
        process_file(str(src), [("exact", "John Doe")], None, False, False)
        assert (tmp_path / "statement_redacted.pdf").exists()

    def test_output_file_created_in_custom_dir(self, tmp_path):
        src = make_pdf(tmp_path, "statement.pdf", ["Name: John Doe"])
        out_dir = tmp_path / "redacted"
        out_dir.mkdir()
        process_file(str(src), [("exact", "John Doe")], str(out_dir), False, False)
        assert (out_dir / "statement_redacted.pdf").exists()

    def test_original_file_untouched(self, tmp_path):
        src = make_pdf(tmp_path, "statement.pdf", ["Name: John Doe"])
        original_text = extract_text(src)
        process_file(str(src), [("exact", "John Doe")], None, False, False)
        assert extract_text(src) == original_text

    def test_returns_match_count(self, tmp_path):
        src = make_pdf(tmp_path, "statement.pdf", ["John Doe\nJohn Doe"])
        count = process_file(str(src), [("exact", "John Doe")], None, False, False)
        assert count >= 2

    def test_unmatched_rule_warning_printed(self, tmp_path, capsys):
        src = make_pdf(tmp_path, "statement.pdf", ["Hello World"])
        process_file(str(src), [("exact", "Jane Smith")], None, False, False)
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Jane Smith" in captured.out


# ---------------------------------------------------------------------------
# collect_input_files
# ---------------------------------------------------------------------------

class TestCollectInputFiles:
    def test_explicit_files_returned(self, tmp_path):
        pdf = make_pdf(tmp_path, "a.pdf", ["text"])
        result = collect_input_files([str(pdf)], None)
        assert str(pdf) in result

    def test_dir_collects_pdfs(self, tmp_path):
        make_pdf(tmp_path, "a.pdf", ["text"])
        make_pdf(tmp_path, "b.pdf", ["text"])
        result = collect_input_files([], str(tmp_path))
        names = [Path(p).name for p in result]
        assert "a.pdf" in names
        assert "b.pdf" in names

    def test_dir_ignores_non_pdfs(self, tmp_path):
        make_pdf(tmp_path, "a.pdf", ["text"])
        (tmp_path / "notes.txt").write_text("not a pdf")
        result = collect_input_files([], str(tmp_path))
        names = [Path(p).name for p in result]
        assert "notes.txt" not in names

    def test_files_and_dir_combined(self, tmp_path):
        extra_dir = tmp_path / "extra"
        extra_dir.mkdir()
        pdf1 = make_pdf(tmp_path, "explicit.pdf", ["text"])
        make_pdf(extra_dir, "batch.pdf", ["text"])
        result = collect_input_files([str(pdf1)], str(extra_dir))
        names = [Path(p).name for p in result]
        assert "explicit.pdf" in names
        assert "batch.pdf" in names

    def test_invalid_dir_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            collect_input_files([], str(tmp_path / "nonexistent"))
