"""Optical character recognition for scanned notices.

WHY THIS EXISTS, AND WHY IT IS SHAPED THE WAY IT IS
---------------------------------------------------
`intake.py` used to stop at a scanned notice and say so honestly. The honesty
was right; stopping was not. A large share of state-authority notices — the
exact segment this product was rebuilt against — arrive as image-only PDFs:
printed, signed, stamped, scanned, mailed. A tool that cannot read them is a
tool that does not work on the user's notice, and there is no second attempt.

Three decisions follow from the product's existing principles rather than from
convenience, and none of them should be reversed for a quieter dependency
story:

**Local only.** The engine runs in-process. Cloud OCR was rejected outright: a
page image cannot be anonymised before it is uploaded — the client's name,
GSTIN and the officer's signature are pixels in the scan — so any cloud OCR
call would break the draft tier's guarantee that identifiers never leave the
machine. That guarantee is the reason the draft tier exists.

**Never a hard dependency.** The engine lives behind `available()`. If it is
not installed the product behaves exactly as it did before this module was
added: it reports the scan honestly and asks for the text. Installing it is
one extra:

    uv sync --extra ocr

**Confidence travels with the text.** The engine returns a per-line
confidence, and this module keeps it. A figure read at 0.62 confidence is not
the same fact as a figure read at 0.99, and the difference has to reach the
reviewer. `intake` marks every OCR-derived field so the review UI can show it
in the must-confirm state — the same treatment `amount_unread` already gets,
for the same reason. The rule from `CLAUDE.md` holds unchanged: a blank the
reviewer can see is safe, a wrong figure they cannot see is not.

WHY RAPIDOCR AND NOT TESSERACT
------------------------------
Tesseract is the obvious choice and was rejected on deployment grounds. It
needs a system binary installed outside Python — a different install route on
Windows, macOS and each Linux distribution, and the firms this product is for
run Windows and have no one to install it. RapidOCR ships as an ordinary
Python wheel with its models bundled and its runtime (ONNX) in the wheel too,
so `pip install` is the whole story on every platform. For a self-hosted tool
in a five-partner firm that difference decides whether the feature exists.

PAGE RENDERING
--------------
`pypdfium2`, also a pure wheel, rasterises the PDF. DPI is a real quality
setting for this work: departmental scans are often 200 DPI originals with
small tabular figures, and rendering below 300 gives visibly worse readings on
exactly the annexure rows the amounts come from.
"""

import io
import os
from typing import Any, Dict, List, Optional, Tuple

# Rendering resolution. 300 is the floor at which annexure tables read
# reliably; below it the digits in a rupee column start to merge.
OCR_DPI = int(os.getenv("OCR_DPI", "300"))

# A hard cap on work. A scanned notice with a hundred-page annexure would
# otherwise take minutes and produce a document nobody reads; the operative
# part of a notice is never that long.
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "40"))

# Below this, a line is reported as doubtful rather than trusted. 0.80 is
# deliberately conservative: the cost of flagging a good line is that a
# reviewer glances at it, and the cost of trusting a bad one is a wrong figure
# in a filed reply.
OCR_MIN_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "0.80"))

# Rows within this many pixels of each other are the same line of text. Set
# against a 300 DPI render, where a line of body text is roughly 40px tall.
_ROW_TOLERANCE = 14

_engine = None
_engine_error: Optional[str] = None


def available() -> Tuple[bool, Optional[str]]:
    """
    Whether OCR can run here, and if not, why not.

    The reason is returned rather than logged because it belongs in front of
    the user: "install the OCR extra" is an action they can take, and a silent
    fallback to "this notice appears to be scanned" is not.
    """
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False, ("PDF rendering is not installed. Install the OCR extra "
                       "to read scanned notices: uv sync --extra ocr")
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False, ("The OCR engine is not installed. Install the OCR extra "
                       "to read scanned notices: uv sync --extra ocr")
    return True, None


def _get_engine():
    """
    Load the engine once and keep it.

    Construction loads the detection and recognition models and costs a second
    or two. Doing that per page — or per upload — would make OCR look far
    slower than it is.
    """
    global _engine, _engine_error
    if _engine is not None:
        return _engine
    if _engine_error is not None:
        raise RuntimeError(_engine_error)
    try:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    except Exception as e:                      # pragma: no cover - env specific
        _engine_error = f"The OCR engine could not be started: {e}"
        raise RuntimeError(_engine_error)
    return _engine


def _render_pages(content: bytes, dpi: int, max_pages: int) -> List[Any]:
    """Rasterise a PDF into numpy arrays, one per page."""
    import numpy as np
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(io.BytesIO(content))
    try:
        count = min(len(document), max_pages)
        pages = []
        for index in range(count):
            page = document[index]
            # pdfium's scale is relative to 72 DPI.
            bitmap = page.render(scale=dpi / 72)
            pages.append(np.asarray(bitmap.to_pil().convert("RGB")))
        return pages
    finally:
        document.close()


def _lines_from_result(result: Any) -> List[Dict[str, Any]]:
    """
    Turn the engine's box list into text lines, in reading order.

    This reconstruction is not cosmetic. Two consumers depend on the shape of
    the text and would silently misread a flat token stream:

    - `defects.segment()` finds limb headings by line structure, so a lost
      newline merges two limbs into one.
    - `notice_tables` reads a row of head-wise figures as a row, and validates
      it against the total printed on that same row. Boxes joined in the wrong
      order produce a row that fails its own checksum and is correctly — but
      needlessly — discarded.

    So boxes are grouped into rows by vertical position and ordered left to
    right within a row, which is how a table was printed and how it must come
    back.
    """
    if not result:
        return []

    boxes = []
    for entry in result:
        try:
            box, text, confidence = entry[0], entry[1], entry[2]
        except (IndexError, TypeError):
            continue
        if not text or not str(text).strip():
            continue
        ys = [float(point[1]) for point in box]
        xs = [float(point[0]) for point in box]
        boxes.append({
            "text": str(text).strip(),
            "confidence": float(confidence),
            "top": min(ys),
            "left": min(xs),
        })

    if not boxes:
        return []

    boxes.sort(key=lambda b: (b["top"], b["left"]))

    rows: List[List[Dict[str, Any]]] = [[boxes[0]]]
    for box in boxes[1:]:
        # Compare against the row's first box rather than a running mean: on a
        # table row with tall and short cells a drifting mean eventually
        # swallows the next row.
        if abs(box["top"] - rows[-1][0]["top"]) <= _ROW_TOLERANCE:
            rows[-1].append(box)
        else:
            rows.append([box])

    lines = []
    for row in rows:
        row.sort(key=lambda b: b["left"])
        text = " ".join(b["text"] for b in row)
        lines.append({
            "text": text,
            # The weakest box governs the line. A row is only as trustworthy
            # as its least legible cell, and in an annexure that cell is
            # usually the figure.
            "confidence": min(b["confidence"] for b in row),
        })
    return lines


def ocr_pdf(content: bytes, dpi: int = None, max_pages: int = None) -> Dict[str, Any]:
    """
    Read a scanned PDF.

    Returns the text plus everything the reviewer needs to judge it: how many
    pages were read, the mean and minimum confidence, and every line the
    engine was unsure about. Raises RuntimeError when OCR is unavailable —
    callers decide whether that is fatal, and in `intake` it is not.
    """
    ok, reason = available()
    if not ok:
        raise RuntimeError(reason)

    dpi = dpi or OCR_DPI
    max_pages = max_pages or OCR_MAX_PAGES

    engine = _get_engine()
    pages = _render_pages(content, dpi, max_pages)

    page_texts: List[str] = []
    all_lines: List[Dict[str, Any]] = []
    for page in pages:
        try:
            result, _ = engine(page)
        except Exception:
            # One unreadable page must not lose the other thirty-nine.
            page_texts.append("")
            continue
        lines = _lines_from_result(result)
        all_lines.extend(lines)
        page_texts.append("\n".join(line["text"] for line in lines))

    text = "\n\n".join(t for t in page_texts if t)
    confidences = [line["confidence"] for line in all_lines]
    doubtful = [line for line in all_lines
                if line["confidence"] < OCR_MIN_CONFIDENCE]

    return {
        "text": text,
        "pages_read": len(pages),
        "lines": len(all_lines),
        "mean_confidence": (round(sum(confidences) / len(confidences), 3)
                            if confidences else None),
        "min_confidence": round(min(confidences), 3) if confidences else None,
        # Capped: a reviewer will read ten doubtful lines and will not read
        # four hundred, and a list that long says the scan itself is the
        # problem rather than any particular line.
        "doubtful_lines": [
            {"text": line["text"], "confidence": round(line["confidence"], 3)}
            for line in doubtful[:12]
        ],
        "doubtful_count": len(doubtful),
        "dpi": dpi,
        "truncated": len(pages) >= max_pages,
    }


def describe_quality(result: Dict[str, Any]) -> List[str]:
    """
    Warnings a reviewer should see before they trust an OCR read.

    Phrased as instructions rather than diagnostics. "Mean confidence 0.71"
    tells a partner nothing they can act on; "check every figure against the
    notice" does.
    """
    warnings: List[str] = []
    if not result.get("text"):
        warnings.append(
            "This notice was scanned and no text could be recovered from the "
            "image. Upload a clearer scan, or paste the text of the notice."
        )
        return warnings

    warnings.append(
        f"This notice was read by OCR from a scanned image "
        f"({result.get('pages_read', 0)} page(s)). Every figure and date below "
        "was machine-read and must be checked against the notice before the "
        "panel is run."
    )

    mean = result.get("mean_confidence")
    if mean is not None and mean < 0.90:
        warnings.append(
            f"The scan is of poor quality (average confidence "
            f"{mean:.0%}). Treat every extracted figure as unconfirmed."
        )

    doubtful = result.get("doubtful_count") or 0
    if doubtful:
        warnings.append(
            f"{doubtful} line(s) could not be read with confidence. "
            "These are listed against the extraction for checking."
        )

    if result.get("truncated"):
        warnings.append(
            f"Only the first {result.get('pages_read')} pages were read. "
            "If defects appear beyond that point, upload the remaining pages "
            "as a separate document."
        )
    return warnings
