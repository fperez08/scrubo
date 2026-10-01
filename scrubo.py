import argparse
import re
import sys
from pathlib import Path

import pymupdf as fitz


def load_rules(rules_file: str) -> list[tuple[str, str]]:
    rules = []
    with open(rules_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("regex:"):
                rules.append(("regex", line[6:].strip()))
            else:
                rules.append(("exact", line))
    return rules


def find_rects_for_exact(page: fitz.Page, term: str, case_sensitive: bool) -> list[fitz.Rect]:
    rects = page.search_for(term)
    if not case_sensitive:
        return rects
    # search_for is always case-insensitive in PyMuPDF; filter by reading the actual text in each rect.
    return [r for r in rects if term in page.get_textbox(r)]


def find_rects_for_regex(page: fitz.Page, pattern: str, case_sensitive: bool) -> list[fitz.Rect]:
    re_flags = 0 if case_sensitive else re.IGNORECASE
    page_text = page.get_text()
    compiled = re.compile(pattern, re_flags)
    # Each matched_str carries exact casing from the PDF; search_for will locate it.
    unique_matches = {m.group() for m in compiled.finditer(page_text) if m.group().strip()}
    rects = []
    for matched_str in unique_matches:
        rects.extend(page.search_for(matched_str))
    return rects


def redact_pdf(
    input_path: str,
    rules: list[tuple[str, str]],
    output_path: str,
    case_sensitive: bool,
    verbose: bool,
) -> dict[str, int]:
    doc = fitz.open(input_path)
    match_counts: dict[str, int] = {}

    for page_num, page in enumerate(doc):
        page_had_matches = False

        for rule_type, pattern in rules:
            label = f"regex:{pattern}" if rule_type == "regex" else pattern

            if rule_type == "exact":
                rects = find_rects_for_exact(page, pattern, case_sensitive)
            else:
                rects = find_rects_for_regex(page, pattern, case_sensitive)

            for rect in rects:
                page.add_redact_annot(rect, fill=(0, 0, 0))
                match_counts[label] = match_counts.get(label, 0) + 1
                page_had_matches = True
                if verbose:
                    print(f"    Page {page_num + 1}: '{label}' at {rect}")

        if page_had_matches:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    doc.save(output_path)
    doc.close()
    return match_counts


def process_file(
    input_path: str,
    rules: list[tuple[str, str]],
    output_dir: str | None,
    case_sensitive: bool,
    verbose: bool,
) -> int:
    src = Path(input_path)
    dest_dir = Path(output_dir) if output_dir else src.parent
    output_path = dest_dir / (src.stem + "_redacted.pdf")

    print(f"\nProcessing: {src}")

    match_counts = redact_pdf(str(src), rules, str(output_path), case_sensitive, verbose)

    total = sum(match_counts.values())
    print(f"  Output:    {output_path}")

    if total == 0:
        print("  WARNING: no rules matched anything in this file.")
    else:
        for label, count in match_counts.items():
            print(f"  Removed '{label}': {count} occurrence(s)")

    # Warn about rules that produced zero matches.
    for rule_type, pattern in rules:
        label = f"regex:{pattern}" if rule_type == "regex" else pattern
        if label not in match_counts:
            print(f"  WARNING: rule '{label}' matched nothing in this file")

    return total


def collect_input_files(files: list[str], directory: str | None) -> list[str]:
    paths = list(files)
    if directory:
        dir_path = Path(directory)
        if not dir_path.is_dir():
            print(f"Error: --dir '{directory}' is not a directory.")
            sys.exit(1)
        paths.extend(str(p) for p in sorted(dir_path.glob("*.pdf")))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="scrubo",
        description="Redact PII from PDF files by truly removing text content.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Rules file format (one entry per line):
  John Doe                        exact string match
  regex:\\d{4}[-\\s]\\d{4}         regex pattern

Examples:
  python scrubo.py statement.pdf --rules rules.txt
  python scrubo.py jan.pdf feb.pdf --rules rules.txt --output ./redacted/
  python scrubo.py --dir ./statements/ --rules rules.txt --verbose
  python scrubo.py report.pdf --rules rules.txt --redact "Extra Term"
        """,
    )
    parser.add_argument("files", nargs="*", help="PDF file(s) to process")
    parser.add_argument("--dir", metavar="DIR", help="Directory of PDFs to process")
    parser.add_argument("--rules", metavar="FILE", help="Rules file (see format above)")
    parser.add_argument(
        "--redact",
        action="append",
        default=[],
        metavar="TERM",
        help="Additional exact term to redact (repeatable)",
    )
    parser.add_argument("--output", metavar="DIR", help="Output directory for redacted files")
    parser.add_argument("--verbose", action="store_true", help="Show per-page match details")
    parser.add_argument(
        "--case-sensitive", action="store_true", help="Use case-sensitive matching (default: insensitive)"
    )

    args = parser.parse_args()

    # Build rules list.
    rules: list[tuple[str, str]] = []
    if args.rules:
        rules.extend(load_rules(args.rules))
    for term in args.redact:
        rules.append(("exact", term))

    if not rules:
        parser.error("no rules specified — use --rules FILE and/or --redact TERM")

    # Collect PDFs.
    input_files = collect_input_files(args.files, args.dir)
    if not input_files:
        parser.error("no input files specified — provide file paths or use --dir")

    # Ensure output directory exists.
    if args.output:
        Path(args.output).mkdir(parents=True, exist_ok=True)

    # Process each file.
    total_files = 0
    total_matches = 0

    for path in input_files:
        p = Path(path)
        if not p.exists():
            print(f"WARNING: file not found, skipping: {path}")
            continue
        if p.suffix.lower() != ".pdf":
            print(f"WARNING: not a PDF, skipping: {path}")
            continue
        total_matches += process_file(path, rules, args.output, args.case_sensitive, args.verbose)
        total_files += 1

    print(f"\nDone. {total_files} file(s) processed, {total_matches} total occurrence(s) removed.")


if __name__ == "__main__":
    main()
