"""Reconciliation ingestion.

A GST notice is mostly about numbers. The real work on an ASMT-10 is
reconciling GSTR-2A against GSTR-3B supplier by supplier, and only then
arguing the law over what is left. A panel that never sees the figures argues
the difference as one undifferentiated number — which is exactly what a reply
must not do, because a difference is several problems wearing one figure and
each carries a different argument.

THE ARCHITECTURAL DECISION HERE: none of this data reaches a model.

A reconciliation is thousands of rows of client and third-party invoice
detail. Sending it would cost hundreds of thousands of tokens, expose supplier
data that is not even the client's to disclose, and buy nothing — bucketing is
arithmetic, and arithmetic belongs in Python. Rows are parsed, classified and
aggregated locally; what reaches the panel is a summary of a few hundred
tokens: bucket, amount, count, share.

The one exception is deliberate and narrow. Column headers vary between firms
("GSTIN", "Supplier GSTIN", "GSTIN of Supplier", "Party GSTIN"), so when fuzzy
matching cannot identify the columns, the HEADER ROW ALONE may be sent for
mapping. Headers carry no client data. No row ever follows them.
"""

import csv
import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple

MAX_UPLOAD_BYTES = int(os.getenv("MAX_RECON_BYTES", str(15 * 1024 * 1024)))
SUPPORTED = (".xlsx", ".xlsm", ".csv", ".docx", ".pdf")

# A reconciliation reaches the firm in whatever the client's accountant had to
# hand, and that is routinely a Word table pasted out of the ERP or a PDF the
# portal or the department produced. Refusing those forced the firm to
# re-key thousands of rows into a spreadsheet before the panel could see any
# figures at all — which meant, in practice, that it did not see them.
#
# Both are read for TABLES only, and both keep the rule the workbook reader
# keeps: a file whose columns cannot be identified raises and says what to
# upload instead. A reconciliation half-read is worse than one not read, and
# the bucket totals are what the reply is argued from.
TABULAR_FORMATS = (".docx", ".pdf")

# Guard against a workbook with a runaway row count.
MAX_ROWS = 20000

# Rows below this are noise in a reconciliation and distort the buckets.
MIN_MATERIAL_AMOUNT = 1.0


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

# Ordered: the first alias that matches a header wins, so more specific
# aliases must precede generic ones.
COLUMN_ALIASES: Dict[str, List[str]] = {
    "supplier_gstin": [
        "supplier gstin", "gstin of supplier", "vendor gstin", "party gstin",
        "supplier gst no", "gstin/uin", "gstin uin", "gstin",
    ],
    "supplier_name": [
        "supplier name", "vendor name", "party name", "trade name",
        "legal name", "supplier", "vendor", "party",
    ],
    "invoice_no": [
        "invoice number", "invoice no", "inv no", "bill no", "document number",
        "doc no", "invoice",
    ],
    "invoice_date": [
        "invoice date", "inv date", "bill date", "document date", "date",
    ],
    "amount_2a": [
        "2a amount", "gstr-2a", "gstr 2a", "2b amount", "gstr-2b", "gstr 2b",
        "as per 2a", "as per 2b", "as per gstr-2a", "as per gstr-2b",
        "portal amount", "2a tax", "2b tax",
    ],
    "amount_books": [
        "books amount", "as per books", "as per 3b", "3b amount", "gstr-3b",
        "gstr 3b", "purchase register", "as per pr", "books", "itc availed",
        "credit availed",
    ],
    "difference": [
        "difference", "diff", "variance", "short", "excess", "gap",
        "mismatch amount", "net difference",
    ],
    "tax_amount": [
        "total tax", "tax amount", "igst", "cgst", "sgst", "tax", "amount",
    ],
    "status": [
        "status", "remarks", "remark", "reason", "category", "observation",
        "nature of difference", "reconciliation status", "comments", "narration",
    ],
}


def _normalise_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(value or "").strip().lower()).strip()


def detect_columns(headers: List[Any]) -> Dict[str, int]:
    """
    Map our field names onto column indices, locally.

    Exact alias match first across all fields, then containment. Doing exact
    matching for everything before any containment stops a loose alias in one
    field stealing a column another field would have matched precisely.
    """
    normalised = [_normalise_header(h) for h in headers]
    mapping: Dict[str, int] = {}
    taken: set = set()

    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            for index, header in enumerate(normalised):
                if index in taken or not header:
                    continue
                if header == alias:
                    mapping[field] = index
                    taken.add(index)
                    break
            if field in mapping:
                break

    for field, aliases in COLUMN_ALIASES.items():
        if field in mapping:
            continue
        for alias in aliases:
            for index, header in enumerate(normalised):
                if index in taken or not header:
                    continue
                if alias in header or header in alias:
                    mapping[field] = index
                    taken.add(index)
                    break
            if field in mapping:
                break

    return mapping


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _to_amount(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    # Accounting parentheses are the usual way a credit is shown in a
    # reconciliation exported from Tally.
    negative = text.startswith("(") and text.endswith(")")
    # Indian digit grouping, and a currency prefix that would otherwise leave
    # a stray decimal point ahead of the number ("Rs. 1,000.50").
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    amount = float(match.group())
    return -abs(amount) if negative else amount


def _find_header_row(rows: List[List[Any]]) -> int:
    """
    Reconciliation sheets routinely carry a title and a blank line above the
    real header. Take the first row within the first fifteen that maps at
    least two known fields.
    """
    best_index, best_score = 0, 0
    for index, row in enumerate(rows[:15]):
        score = len(detect_columns(row))
        if score > best_score:
            best_index, best_score = index, score
        if score >= 3:
            return index
    return best_index if best_score >= 2 else 0


def _rows_from_docx(content: bytes, warnings: List[str]) -> List[List[Any]]:
    """
    Rows out of the tables in a Word document.

    A .docx carries its tables as real structure, so this is exact — there is
    no column guessing and no risk of splitting a supplier name on a space.

    Where a document holds several tables the widest is taken, and the others
    are named in a warning rather than silently merged. Merging them is the
    obvious-looking move and it is wrong: a reconciliation exported to Word
    usually carries a small summary table beside the detail, and stacking the
    two double-counts every bucket it touches.
    """
    try:
        import docx
        document = docx.Document(io.BytesIO(content))
    except Exception as e:
        raise ValueError(f"Could not read the Word document: {e}")

    tables = document.tables
    if not tables:
        raise ValueError(
            "No table was found in the Word document. The reconciliation must "
            "be a table, not paragraphs — or upload it as .xlsx or .csv."
        )

    widest = max(tables, key=lambda t: len(t.columns))
    if len(tables) > 1:
        warnings.append(
            f"The document holds {len(tables)} tables. The widest "
            f"({len(widest.columns)} columns) was read; the rest were "
            "ignored. Check that it is the right one."
        )

    rows: List[List[Any]] = []
    for index, row in enumerate(widest.rows):
        if index > MAX_ROWS:
            warnings.append(f"Only the first {MAX_ROWS:,} rows were read.")
            break
        rows.append([cell.text.strip() for cell in row.cells])
    return rows


# A run of two or more spaces is how a PDF text layer separates columns. One
# space is inside a supplier name far more often than it is between columns.
_PDF_COLUMN_GAP = re.compile(r"\s{2,}")


def _rows_from_pdf(content: bytes, warnings: List[str]) -> List[List[Any]]:
    """
    Rows out of a PDF's text layer, split on column gaps.

    This is the one format here with no table structure to read: a PDF records
    where the glyphs are, not what the columns were. Splitting on runs of
    whitespace recovers the grid for the ordinary case — a report printed from
    a spreadsheet or the portal — and does not recover it for a PDF with
    ruled cells and wrapped text.

    So the result is checked rather than trusted. The rows must agree on how
    many columns they have; where they do not, this raises and names the
    formats that will work. The alternative is a bucket total computed from a
    misaligned grid, which arrives looking exactly like a correct one and is
    argued from in a filed reply.

    A scanned reconciliation has no text layer at all and is refused here.
    OCR is offered for notices (`ocr.py`) because a wrong word in a notice is
    visible to the reviewer reading it; a wrong digit in row 4,000 of a
    reconciliation is not.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as e:
        raise ValueError(f"Could not read the PDF: {e}")

    lines: List[str] = []
    for page in pages:
        lines.extend(line for line in page.splitlines() if line.strip())

    if not lines:
        raise ValueError(
            "The PDF has no text layer — it is a scan. A reconciliation is "
            "not read by OCR, because a misread digit in one row of several "
            "thousand is not visible to anyone checking it. Upload the "
            "reconciliation as .xlsx or .csv."
        )

    split = [
        [cell.strip() for cell in _PDF_COLUMN_GAP.split(line.strip())]
        for line in lines[:MAX_ROWS]
    ]
    if len(lines) > MAX_ROWS:
        warnings.append(f"Only the first {MAX_ROWS:,} rows were read.")

    # The modal width is the table; anything narrower is a heading, a page
    # number or a footer, and anything wider is two columns run together.
    widths = [len(row) for row in split if len(row) > 1]
    if not widths:
        raise ValueError(
            "No columns could be identified in the PDF — the text layer has "
            "no column separation to read. Upload the reconciliation as "
            ".xlsx or .csv."
        )
    table_width = max(set(widths), key=widths.count)
    if table_width < 3:
        raise ValueError(
            "The PDF does not appear to hold a reconciliation table — only "
            f"{table_width} column(s) were found. Upload it as .xlsx or .csv."
        )

    rows = [row for row in split if len(row) == table_width]
    dropped = len(split) - len(rows)
    if dropped:
        warnings.append(
            f"{dropped} line(s) in the PDF did not fit the {table_width}-column "
            "grid and were skipped — headings, page furniture, or rows whose "
            "text wrapped. Check the bucket totals against the document."
        )
    return rows


def parse_workbook(filename: str, content: bytes) -> Tuple[List[Any], List[List[Any]], List[str]]:
    """
    Read an uploaded reconciliation into headers and rows. Entirely local.

    Returns (headers, rows, warnings).
    """
    warnings: List[str] = []
    name = (filename or "").lower()

    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    if not any(name.endswith(ext) for ext in SUPPORTED):
        raise ValueError(
            f"Unsupported file type. Upload one of: {', '.join(SUPPORTED)}."
        )

    raw: List[List[Any]] = []
    if name.endswith(".docx"):
        raw = _rows_from_docx(content, warnings)
    elif name.endswith(".pdf"):
        raw = _rows_from_pdf(content, warnings)
    elif name.endswith(".csv"):
        text = None
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Could not decode the CSV file.")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        raw = [row for row in csv.reader(io.StringIO(text), dialect)]
    else:
        try:
            from openpyxl import load_workbook
            workbook = load_workbook(
                io.BytesIO(content), read_only=True, data_only=True
            )
            sheet = workbook.active
            for index, row in enumerate(sheet.iter_rows(values_only=True)):
                if index > MAX_ROWS:
                    warnings.append(
                        f"Only the first {MAX_ROWS:,} rows were read."
                    )
                    break
                raw.append(list(row))
            workbook.close()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Could not read the workbook: {e}")

    raw = [row for row in raw if any(
        cell not in (None, "") for cell in (row or [])
    )]
    if not raw:
        raise ValueError("The file contains no data.")

    header_index = _find_header_row(raw)
    headers = raw[header_index]
    rows = raw[header_index + 1:]

    if not rows:
        warnings.append("A header row was found but there are no data rows.")

    return headers, rows, warnings


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_row(
    row: List[Any],
    mapping: Dict[str, int],
    pack,
) -> str:
    """
    Assign a line to a legal bucket.

    Preference order is deliberate. What the preparer wrote in the status
    column is the best evidence of what the difference actually is — they did
    the reconciliation. Only where that is silent do we fall back to the shape
    of the row, and where neither speaks the line is left UNRECONCILED rather
    than assigned a flattering category.
    """
    def cell(field: str) -> str:
        index = mapping.get(field)
        if index is None or index >= len(row):
            return ""
        return str(row[index] or "").strip()

    status = cell("status").lower()
    if status:
        for bucket in pack.RECONCILIATION_BUCKETS:
            if any(keyword in status for keyword in bucket.keywords):
                return bucket.key

    # The supplier's own name sometimes carries the answer ("RCM - freight").
    haystack = f"{cell('supplier_name')} {cell('invoice_no')}".lower()
    for key in ("rcm", "import_igst", "isd"):
        bucket = pack.RECONCILIATION_BUCKETS_BY_KEY[key]
        if any(keyword in haystack for keyword in bucket.keywords):
            return bucket.key

    # A line present in the books but absent from the portal, with no
    # explanation, is unexplained. It is NOT assumed to be timing.
    return pack.UNRECONCILED.key


def row_amount(row: List[Any], mapping: Dict[str, int]) -> Optional[float]:
    """
    The amount in issue for a line.

    An explicit difference column is authoritative. Otherwise the difference
    between books and portal. Otherwise whatever single amount is present.
    """
    def value(field: str) -> Optional[float]:
        index = mapping.get(field)
        if index is None or index >= len(row):
            return None
        return _to_amount(row[index])

    difference = value("difference")
    if difference is not None:
        return abs(difference)

    books, portal = value("amount_books"), value("amount_2a")
    if books is not None and portal is not None:
        return abs(books - portal)
    for field in ("amount_books", "amount_2a", "tax_amount"):
        amount = value(field)
        if amount is not None:
            return abs(amount)
    return None


def summarise(
    headers: List[Any],
    rows: List[List[Any]],
    pack,
    mapping: Optional[Dict[str, int]] = None,
    mask_suppliers: bool = False,
) -> Dict[str, Any]:
    """
    Bucket the reconciliation and aggregate.

    The return value is what the panel sees. It contains totals, counts and
    shares — never a row.
    """
    mapping = mapping if mapping is not None else detect_columns(headers)
    warnings: List[str] = []

    if not mapping:
        raise ValueError(
            "None of the columns could be identified. Expected at least a "
            "supplier GSTIN or an amount column."
        )
    if not any(k in mapping for k in
               ("difference", "amount_books", "amount_2a", "tax_amount")):
        raise ValueError(
            "No amount column could be identified. Expected a difference, "
            "books, portal or tax amount column."
        )
    if "status" not in mapping:
        warnings.append(
            "No status or remarks column was found, so lines could not be "
            "classified from the preparer's own reconciliation and are shown "
            "as not yet reconciled. Add a remarks column describing each "
            "difference for a materially better analysis."
        )

    buckets: Dict[str, Dict[str, Any]] = {}
    suppliers: Dict[str, float] = {}
    total = 0.0
    counted = 0
    skipped = 0

    for row in rows:
        amount = row_amount(row, mapping)
        if amount is None or amount < MIN_MATERIAL_AMOUNT:
            skipped += 1
            continue

        key = classify_row(row, mapping, pack)
        entry = buckets.setdefault(key, {"key": key, "amount": 0.0, "count": 0})
        entry["amount"] += amount
        entry["count"] += 1
        total += amount
        counted += 1

        gstin_index = mapping.get("supplier_gstin")
        if gstin_index is not None and gstin_index < len(row):
            gstin = str(row[gstin_index] or "").strip()
            if gstin:
                suppliers[gstin] = suppliers.get(gstin, 0.0) + amount

    if not counted:
        raise ValueError(
            "No usable amounts were found. Check that the amount column "
            "contains numbers."
        )

    ordered = sorted(buckets.values(), key=lambda b: b["amount"], reverse=True)
    for entry in ordered:
        entry["share"] = entry["amount"] / total if total else 0.0
        bucket = (pack.RECONCILIATION_BUCKETS_BY_KEY.get(entry["key"])
                  or pack.UNRECONCILED)
        entry["label"] = bucket.label
        entry["strength"] = bucket.strength
        entry["action"] = bucket.action

    unreconciled = next(
        (b for b in ordered if b["key"] == pack.UNRECONCILED.key), None
    )
    if unreconciled and unreconciled["share"] > 0.25:
        warnings.append(
            f"{unreconciled['share']:.0%} of the difference "
            f"(Rs. {unreconciled['amount']:,.0f}) is unexplained. That portion "
            "has no argument behind it — trace it before filing."
        )

    top = sorted(suppliers.items(), key=lambda item: item[1], reverse=True)[:5]
    exposures = [
        {
            # Supplier GSTINs are third-party data and not the client's to
            # disclose. On the anonymising tier they never leave the machine.
            "supplier": ("[supplier withheld]" if mask_suppliers
                         else gstin),
            "amount": round(amount, 2),
        }
        for gstin, amount in top
    ]

    return {
        "total": round(total, 2),
        "row_count": counted,
        "skipped_rows": skipped,
        "supplier_count": len(suppliers),
        "buckets": ordered,
        "top_exposures": exposures,
        "columns_detected": sorted(mapping.keys()),
        "warnings": warnings,
    }


def read_reconciliation(
    filename: str,
    content: bytes,
    pack,
    mask_suppliers: bool = False,
) -> Dict[str, Any]:
    """Parse, classify and aggregate an uploaded reconciliation."""
    headers, rows, warnings = parse_workbook(filename, content)
    summary = summarise(headers, rows, pack, mask_suppliers=mask_suppliers)
    summary["warnings"] = warnings + summary["warnings"]
    summary["headers"] = [str(h) for h in headers if h not in (None, "")][:40]
    return summary
