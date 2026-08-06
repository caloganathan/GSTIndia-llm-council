# Handover — MVP testing round (HISTORICAL)

> **Superseded. Read [`review-2026-08-05-action-plan.md`](review-2026-08-05-action-plan.md)
> first for the current state.**
>
> This file records the state of the MVP testing round. The branch it
> describes (`claude/tax-consulting-ai-review-c6fjvu`) was merged in
> `bad8fa5` and no longer exists, so §3's resume recipe and §7's merge
> instructions no longer apply. §9 (Landmines) and §4 (the corpus loop)
> remain accurate and are the reason this file is kept rather than deleted.
>
> Current suite: run `uv run pytest`, and expect zero failures. CI runs it on
> every push and pull request (`.github/workflows/test.yml`); the four OCR
> end-to-end tests skip without `uv sync --extra ocr` and are forced to run in
> CI via `OCR_REQUIRED=1`.

Written so a fresh session did not have to re-derive any of it from the diff.

---

## 1. Where things stand

The P0 items of `docs/product-review-and-dev-plan.md` are built, plus two P1
items. What is on the branch:

| Area | File | State |
|---|---|---|
| Scanned notices | `backend/ocr.py` | Local RapidOCR + pypdfium2, optional extra, degrades honestly |
| Statutory arithmetic | `backend/calculators.py` | s.50 interest, 73/74 penalty stages, s.107/112 pre-deposit, appeal limitation, s.128A |
| Reply deadlines | `backend/deadlines.py` | Days remaining, urgency bands, worst-first sort, iCalendar export |
| Run cost in rupees | `backend/pricing.py` | Estimated from the firm's own completed matters |
| Batch testing | `evals/batch_extract.py` | **The tool for this round.** No model calls, no cost |
| Golden set | `evals/golden/*.json` | 9 synthetic cases across 8 forms |
| Free scoring | `tests/test_golden_set.py` | Segmentation + figure reading, runs on every push |

Nine extraction bugs were found and fixed while building this. They are
documented in `CLAUDE.md` under *"Catalogue patterns are load-bearing"* — read
that section before touching any pattern.

## 2. What has NOT been verified

**No real panel run has ever happened in these sessions.** The sandbox proxy
blocks OpenRouter (403), so every model-facing path — grounding, the four
counsel, cross-examination, the chairman, citation verification — is covered
only by mocked tests.

The mitigating fact: `panel.py`, `roles.py`, `verification.py`, `sanitizer.py`,
`grounding.py`, `openrouter.py`, `reconciliation.py` and `council.py` are
**byte-identical to master**. The risk is in the shape of the defect records
flowing in, not in the reasoning. But "the tests pass" is not "a partner read
the output", and the first paid run is the real check.

Also unverified: the Docker image has never been built (no daemon in the
sandbox). The `uv sync --frozen --no-dev --no-install-project --extra ocr`
command inside it was verified to resolve and import.

## 3. Resume from a fresh session

> The branch below was merged and deleted. Work from `master`.

```bash
git fetch origin
git checkout master
uv sync --extra ocr
uv run pytest                    # expect zero failures
```

If OCR will not install, `uv sync` alone works — 5 tests skip, nothing fails,
and scanned notices are reported rather than read.

## 4. The corpus loop — this is the work

```bash
uv run python -m evals.batch_extract ~/notices --out ~/testing/round1
```

No model calls. Costs nothing. Writes two files:

- `extraction-report.md` — per notice: what was read, the limb table, whether
  the limbs reconcile, and a **Needs checking** list
- `review-sheet.csv` — columns for the human to fill in

**The reconciliation line is the signal to trust.** It needs no ground truth: a
notice whose limbs do not sum to the total it prints for itself has a real
defect, established without anyone reading the notice.

### Reading the output

| Symptom | Meaning | Fix |
|---|---|---|
| `NO LIMBS SEGMENTED` | Worst outcome. The reply would answer a multi-limb notice as one issue | Add a catalogue pattern (§5) |
| Limb count too low | A heading did not match | Add a catalogue pattern (§5) |
| `LIMBS DO NOT RECONCILE` | A limb absorbed a neighbour's figure, or a figure was misread | Investigate `notice_tables.py` (§6) |
| `limb(s) with no figure read` | Correct behaviour — the product refusing to guess | Reviewer enters it; only a bug if the figure is plainly legible |
| Wrong client / GSTIN / dates | Field pattern gap | `intake.py` regexes |
| `READ BY OCR` | Expected on scans | Check every figure; the flag is the point |

### Turning a real notice into a golden case

Once a real notice's extraction has been checked and corrected, **anonymise it
and add it to the golden set** — this is how the corpus compounds into
permanent regression cover.

Copy `evals/golden/gst-asmt10-multilimb-fy2324.json` as the template. Replace
every identifier with an invented one (name, GSTIN, reference, address,
officer). Keep the *structure* and the *phrasing* of the headings, because that
is what is being tested.

**A test enforces `"synthetic": true` and a `provenance` note on every case.**
These ship in a public repository. A golden case built from a client matter
must never be committed, and the flag exists so that decision stays visible.

## 5. Adding a catalogue pattern (the most common fix)

Patterns live in `backend/domains/gst_defects.py`, in each `DefectType(...)`
call's `_p(...)` list.

**The rule: a pattern must match HEADING language, not statutory prose that
appears in every notice.** Both failure directions have happened:

- A pattern that matches too little → the limb never segments → it is never
  answered → **it is confirmed unopposed**.
- A pattern that matches too much → invents a limb and hands it a neighbour's
  figures.

Bugs already caused by the second kind, all documented in `CLAUDE.md`:

- `e[\s-]?invoic` with no `\b` matched the ordinary phrase **"the invoice"**
- a bare `refund` matched the s.73 boilerplate *"erroneously refunded"*
- a bare `interest under section 50` matched the demand boilerplate on almost
  every notice — **do not add it back**

Workflow:

```bash
# 1. edit the pattern in backend/domains/gst_defects.py
# 2. the free scorer must stay green
uv run pytest tests/test_golden_set.py
# 3. re-run the corpus and confirm the notice now segments
uv run python -m evals.batch_extract ~/notices --out ~/testing/round2
```

Never skip step 2. It is the only thing standing between a widened pattern and
a phantom limb on every other notice.

## 6. If figures are misread

`backend/notice_tables.py` reads head-wise rows using the checksum the table
carries for free: four components summing to their own printed total. Two
guards were added after real failures — do not remove either:

- digits inside hyphenated identifiers (`GSTR-1`, `ASMT-10`) are not tokenised;
  two stray `1`s once summed to within the paisa tolerance of the wrong total,
  passed the checksum, and reported Rs. 42,152 for a Rs. 84,300 limb
- `MAX_ROW_SPAN` requires a head-wise row to have been printed as a row; four
  numbers scattered through prose will occasionally sum to a fifth

## 7. Merge and deploy (the merge itself is done; the deploy notes still hold)

1. ~~Merge the branch to `master`~~ — done in `bad8fa5`.
2. Render rebuilds from `master`. The Dockerfile now installs the OCR extra by
   default (~250 MB). If the image is too large for the plan, rebuild with
   `--build-arg INSTALL_OCR=false`; the app then degrades honestly and shows a
   banner.
3. Set `USD_INR_RATE` in the Render dashboard if 88.0 is stale.
4. On first load, check the dashboard for a red banner. Stale OpenRouter model
   IDs are now named in the UI, not just in a startup log.

New environment variables are documented in `.env.example`: `OCR_DPI`,
`OCR_MAX_PAGES`, `OCR_MIN_CONFIDENCE`, `USD_INR_RATE`,
`ENABLE_GENERAL_COUNCIL`.

## 8. Deliberately not built

From `docs/product-review-and-dev-plan.md`, still open:

- **P1.1 Appeal module** — Statement of Facts and Grounds of Appeal (APL-01).
  The calculators it needs (pre-deposit, appeal limitation) are already built
  and tested. This is the largest remaining item and the current volume market.
- **P1.3** vernacular notices · **P1.5** firm letterhead · **P1.6** matter
  lifecycle
- **All of P2** — hosted multi-tenant, notice discovery, authority curation

## 9. Landmines — do not "improve" these

1. **The two documents never merge.** `build_filing_reply()` and
   `build_file_note()` in `export.py`. `TestTheWallBetweenDocuments` asserts
   every class of leak from both sides.
2. **Cloud OCR is refused on principle.** A page image cannot be anonymised
   before upload, so it would break the draft tier's guarantee.
3. **Reconciliation rows never reach a model.** Only the ~500-token aggregate.
4. **An unverified authority never reaches the filing document.** `_is_filable()`.
5. **`amount_unread` is never filled with a zero.** A blank the reviewer can
   see is safe; a wrong figure they cannot see is not.
6. **The sanitizer leak test is sacred.** A failure there is a confidentiality
   breach, not a bug.
7. **Stage 2 is cross-examination, not ranking.** Do not reintroduce ranking.

## 10. Two loose ends

- ~~Remote branches `claude/review` and `claude/vercel-deploy`~~ — neither
  exists any longer; `git branch -a` shows only `master` and the current
  working branch. Nothing outstanding here.
- The golden set is synthetic and was authored alongside the code it tests. It
  is a genuine regression harness but **not independent validation**. In one
  case (`gst-adt02-audit-findings`) the synthetic wording was changed rather
  than bending the catalogue, because the classification was genuinely
  ambiguous. Real notices are the first true test of the extraction layer.
