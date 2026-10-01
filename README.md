# scrubo

A Python CLI tool that **truly removes** PII from text-based PDF files — not just visually covers it. The underlying text is stripped from the PDF data layer so it cannot be copy-pasted or extracted programmatically.

Built for bank statements, medical reports, and any other PDF where sensitive data needs to be permanently removed before sharing.

---

## Requirements

- Python 3.10+
- [PyMuPDF](https://pymupdf.readthedocs.io/)

```bash
pip install -r requirements.txt
```

---

## Usage

### Single file

```bash
python scrubo.py statement.pdf --rules rules.txt
```

Output: `statement_redacted.pdf` in the same directory.

### Multiple files

```bash
python scrubo.py jan.pdf feb.pdf mar.pdf --rules rules.txt
```

### Entire folder

```bash
python scrubo.py --dir ./statements/ --rules rules.txt
```

### Custom output directory

```bash
python scrubo.py --dir ./statements/ --rules rules.txt --output ./redacted/
```

### One-off term (no rules file needed)

```bash
python scrubo.py report.pdf --redact "Dr. Smith" --redact "Patient ID 9821"
```

### Combine rules file with one-off terms

```bash
python scrubo.py report.pdf --rules rules.txt --redact "Clinic Name"
```

### Verbose mode (shows which page each match was found on)

```bash
python scrubo.py statement.pdf --rules rules.txt --verbose
```

### Case-sensitive matching

```bash
python scrubo.py statement.pdf --rules rules.txt --case-sensitive
```

---

## Rules file format

One rule per line. Blank lines and lines starting with `#` are ignored.

| Prefix | Type | Example |
|--------|------|---------|
| *(none)* | Exact string match | `John Doe` |
| `regex:` | Regular expression | `regex:\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}` |

Matching is **case-insensitive by default**. Use `--case-sensitive` to override.

### Example `rules.txt`

```
# Personal identifiers
John Doe
123 Main Street

# Account number (exact)
9876543210

# Credit/debit card numbers
regex:\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}

# US Social Security Number
regex:\b\d{3}-\d{2}-\d{4}\b

# Phone numbers
regex:\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}

# Email address
regex:[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}
```

---

## CLI reference

```
usage: scrubo [-h] [--dir DIR] [--rules FILE] [--redact TERM]
              [--output DIR] [--verbose] [--case-sensitive]
              [files ...]

positional arguments:
  files             PDF file(s) to process

options:
  --dir DIR         Directory of PDFs to process
  --rules FILE      Rules file (one rule per line)
  --redact TERM     Additional exact term to redact (repeatable)
  --output DIR      Output directory for redacted files
  --verbose         Show per-page match details
  --case-sensitive  Use case-sensitive matching (default: insensitive)
```

---

## Output

- Redacted files are saved as `<original_name>_redacted.pdf`.
- Original files are never modified.
- A summary is printed to the terminal after each file:

```
Processing: statement.pdf
  Output:    statement_redacted.pdf
  Removed 'John Doe': 4 occurrence(s)
  Removed 'regex:\d{4}[-\s]\d{4}...': 2 occurrence(s)
  WARNING: rule '123 Main Street' matched nothing in this file
```

---

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Limitations

- Text-based PDFs only. Scanned (image-based) PDFs are not supported.
- Redaction targets single-line text spans. Terms that wrap across a line break in the PDF may not be matched.
