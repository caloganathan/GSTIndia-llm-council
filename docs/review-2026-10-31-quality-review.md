# Quality review — GSTIndia-llm-council

Review date: 31 Oct 2026
Commit reviewed: `55584f4` (master, merge of PR #28, 16 Oct 2026)
Standard applied: Big Four engagement-quality review (technology risk + tax technical), ISO/IEC 27001:2022 Annex A and SOC 2 CC-series as the control reference; CGST Act 2017 as amended through Finance Act 2026 as the legal reference.
Deployment context stated by the owner: Render Starter plan (512 MB RAM), in live use by the firm on real client notices.

Legend: FACT = observed in code or measured; INFERENCE = reasoned from facts; [Unverified] = not confirmed against a primary source. Severity = Impact x Likelihood: High = client data, filing accuracy or service availability at risk and plausible in normal use; Medium = material defect, needs a workaround or affects a subset of notices; Low = hygiene, should be fixed in the normal cycle.

---

## 1. Conclusion

The product is well above the open-source norm for a professional tool: the design principles (local OCR, enforced anonymisation on the Draft tier, statutory arithmetic in code, never-upgrade citation gate, provenance on every extracted field) are the right ones and are genuinely enforced in code, not just described. 1,009 tests pass with the OCR extra installed; CI is green.

It is not yet at a standard a Big Four technology-risk reviewer would sign for unattended use on client data on a 512 MB single-instance host. Three defects are rated High and should be fixed before the next real notice is processed:

| # | Finding | Why it is High for this deployment |
|---|---|---|
| O-1 | OCR renders all pages into memory before reading (≈1.1 GB for a 40-page scan at 300 DPI) and runs synchronously inside the async request handler on a single uvicorn worker | On 512 MB the process is OOM-killed by a large scan (measured 1,097 MB peak); any scan freezes the server for every other user for the duration (measured 2.4 s/page on an M-series Mac; several times slower on a Starter CPU) |
| O-2 | A PDF whose cover page has a text layer is never OCR'd, so a scanned annexure attached to a digital cover silently loses every head-wise figure, with no warning | Measured: annexure total ₹2,80,470 and IGST ₹12,45,670 MISSING, `source=text-layer`, zero warnings. This is the "wrong figure the reviewer cannot see" failure the codebase's own rule forbids |
| T-1 | Penalty and pre-deposit base sums `amount_by_head` of every limb, including late-fee and interest limbs | s.73(9), s.74A(5)(i) penalty and s.107(6)(b) pre-deposit are percentages of tax; the working prints an overstated figure labelled "Computed on tax of …" |

The OCR usability issue the owner raised (photos and WhatsApp images rejected) is real and is the cheapest fix in this report (O-3). Section 4 contains the OCR improvement specification.

Overall rating: 72/100. Ship-blockers: O-1, O-2, T-1, S-1. Target after Phase 1 of the spec below: 85+.

---

## 2. Scope and method

- Full read of `backend/ocr.py`, `backend/intake.py` (extraction path), `backend/main.py` (upload endpoints), frontend intake surfaces (`PanelWorkspace.jsx`, `shared.jsx`, `DefectList.jsx`, `Dashboard.jsx`, `api.js`), `Dockerfile`, `render.yaml`, CI workflow, README, CLAUDE.md, docs/.
- Delegated deep-reads (results verified by spot-checking the cited lines): security/reliability (`auth.py`, `users.py`, `storage.py`, `config.py`, `openrouter.py`, `sanitizer.py`, `export.py`); tax-technical (`calculators.py`, `deadlines.py`, `domains/*`, `defects.py`, `notice_tables.py`, `reconciliation.py`, `verification.py`, `grounding.py`).
- Executed: `uv sync --extra ocr` on Python 3.12; `OCR_REQUIRED=1 uv run pytest -q` → 1,009 passed, 1 skipped, 19.8 s.
- Empirical OCR probe (synthetic ASMT-10 with head-wise annexure, Indian number grouping, GSTIN, reference and due date) through `intake.extract_document`: clean scan, noisy + 1.5° skew, 90° rotated, 180° rotated, bilingual Hindi header, mixed digital+scanned PDF, 40-page scan, JPG upload. Probe script: `_probe_ocr.py` (not committed).
- GitHub metadata via public API: 29 merged PRs (all from `claude/*` branches), 17 stale merged branches not deleted, no tags or releases, no CODEOWNERS, SECURITY.md or CHANGELOG, repo description still reads "LLM Council works together to answer your hardest questions".

Not in scope: a live paid panel run (no OpenRouter key used); frontend accessibility audit; load testing.

---

## 3. Findings register

### 3.1 OCR and notice intake

| ID | Title | Sev | Evidence (FACT) | Root cause | Recommendation |
|---|---|---|---|---|---|
| O-1 | Whole-document rasterisation in memory; CPU-bound OCR blocks the event loop | High | `ocr.py:124-140` `_render_pages` builds a list of RGB numpy arrays for every page before any OCR runs; measured 26 MB/page, 1,097 MB peak for 40 pages at 300 DPI; `intake.py:1100` calls `extract_document` synchronously inside `async def read_notice_set`; `Dockerfile:50` single uvicorn worker, no `--workers`; `api.js:138` fetch has no timeout; UI shows only "Reading…" (`PanelWorkspace.jsx:358-363`) | Convenience design: render then recognise; no offloading of CPU work | Render and recognise one page at a time and discard the bitmap; run OCR in `asyncio.to_thread` (or a worker process); add a progress channel (SSE or polling) that shows "page 7 of 23"; cap pages by default at 20 with an explicit "read remaining pages" action; set `OMP_NUM_THREADS` to the instance CPU count. See spec §4 |
| O-2 | Per-document (not per-page) OCR decision loses scanned annexures behind a digital cover page | High | `intake.py:412` `if len(text) < MIN_USEFUL_TEXT and name.endswith(".pdf")` — threshold is on the whole document's text layer; measured on mixed PDF: 931 chars of cover text, annexure figures absent, no warning | Decision made once per file; comment at `intake.py:407-411` states the policy explicitly | Decide per page: a page whose text layer yields < N chars (or < 5 % of the characters a 300 DPI render would plausibly carry) is OCR'd; mark each page's source; a document mixing sources carries `source: "mixed"` and the scanned pages' warnings. Add a golden test with a mixed PDF |
| O-3 | Image uploads rejected (JPG, PNG, HEIC, WhatsApp exports, phone photos) | Medium | `intake.py:43` `SUPPORTED = (".pdf", ".docx", ".txt")`; `PanelWorkspace.jsx:353` `accept=".pdf,.docx,.txt"`; measured: `notice.jpg` → "Unsupported file type" | Intake written for portal PDFs; photographs of physical notices not considered | Accept `.jpg .jpeg .png .tif .tiff .heic .webp` and multi-image sets; convert via Pillow (HEIC via `pillow-heif`) to a page list and feed the same OCR path; order multiple images by filename then by EXIF timestamp; show thumbnails so the user can reorder. Owner-reported pain point |
| O-4 | Hindi / regional script silently discarded with high confidence | Medium | Probe: Devanagari header line read as `FORMGSTASMT-10` — the Hindi text vanished, `mean_confidence 0.987`, no doubtful lines. RapidOCR default models are Chinese+Latin (`rapidocr_onnxruntime 1.4.4`) | Model has no Devanagari/Tamil/Kannada character set; absence of text is not a low-confidence event | Short term: detect large unrecognised regions (detection boxes with empty or very short recognition output, or page coverage of boxes vs expected) and warn "Part of this page is in a script the reader cannot read; English content only was extracted". Medium term: offer language packs (PaddleOCR `devanagari`, `ta`, `te`, `kn` models run on the same ONNX runtime) selectable per matter State |
| O-5 | Rotated pages: reading order scrambled, fields lost | Medium | Probe 90°: first extracted lines start mid-document; reply due date `14/08/2025` MISSING; `mean_confidence 0.982` so no warning. 180° read correctly (engine's angle classifier handles inversion) | `_lines_from_result` groups by `top` then `left` (`ocr.py:184-198`); for landscape scans rows are columns | Detect page orientation before recognition: run detection, measure dominant box aspect/angle, rotate the bitmap by 90/270 and re-run; or use pdfium's page `/Rotate` attribute first. Add a 90° fixture to `test_ocr.py` |
| O-6 | Row-grouping tolerance hard-coded for 300 DPI | Low | `ocr.py:75` `_ROW_TOLERANCE = 14` with comment "against a 300 DPI render"; `OCR_DPI` is env-configurable | Constant not scaled | `tolerance = 14 * dpi / 300`; or use median box height × 0.4 per page |
| O-7 | "Doubtful lines" are computed, capped at 12 and never shown | Medium | `ocr.py:257-260` returns `doubtful_lines`; `describe_quality` says "These are listed against the extraction for checking"; grep of `frontend/src` for `doubtful` → 0 hits | UI never wired | Render the doubtful lines under the warnings with their confidence and a "find in notice" link; highlight any extracted field whose snippet overlaps a doubtful line |
| O-8 | No OCR text review or paste-text path | Medium | Warnings tell the user to "paste the text of the notice manually" (`intake.py:420,431,437`; `Dashboard.jsx:73`), but the form has no raw-notice-text field (`gst.py:596-622` — `issues` and `facts` only); the OCR text itself is never shown | Fallback promised in copy, not built | Add a collapsible "Text as read" panel (per page, scanned pages in amber) that is editable; re-run local field extraction on edit ("Re-read fields"). This single screen resolves most reviewer distrust of OCR |
| O-9 | No image pre-processing | Low | `ocr.py:136-137` renders straight to RGB; no deskew, binarisation, contrast or de-noise | Relies on engine robustness | Probe showed the engine tolerated 1.5° skew and salt noise (conf 0.956), so keep this Low; add deskew (Hough/projection) only if real-world fixtures show benefit. Collect anonymised real scans into `evals/scans/` first |
| O-10 | Upload size validated after the full body is read; no magic-byte check; multipart spools >1 MB to disk | Medium | `main.py:488` `await upload.read()` precedes `intake.py:349` size check; `intake.py:353` extension-only; Starlette multipart spools files over 1 MB to a temp file, contradicting "never written to disk" (`main.py:472`, README) | Framework default not considered | Enforce size while streaming; check `%PDF-` / `PK\x03\x04` / JPEG-PNG magic; cap files per request (5); correct the README claim or set `spool_max_size` high and document the temp-file behaviour |
| O-11 | Render request timeout vs OCR duration | Medium | 2.4 s/page measured locally; Starter CPU is materially slower [Unverified multiplier]; Render's HTTP proxy closes idle responses at ~100 s [Unverified — confirm in Render docs] | Long synchronous request | Resolved by the asynchronous job design in §4 regardless of the exact limit |

### 3.2 Tax-technical (delegated review, spot-checked)

| ID | Title | Sev | Evidence | Correct position | Recommendation |
|---|---|---|---|---|---|
| T-1 | Penalty / pre-deposit base includes non-tax limbs | High | `calculators.py:1121-1132` sums every limb's `amount_by_head`; `export.py:1308` prints "Computed on tax of …" | s.73(9), s.74(9), s.74A(5) penalty is a % of tax; s.107(6)(b) 10 % of "tax in dispute"; late fee (s.47) and interest (s.50) are not tax | Exclude limb types `late_fee`, `interest_delayed_payment`, `penalty_general`, e-way bill penalty from the base; print excluded amounts in the working; add a test |
| T-2 | "Pre-deposit payable from Electronic Cash Ledger only" stated as settled | High | `gst.py:244-250` | Contested: Circular 172/04/2022-GST para 6 and Oasis Realty (Bom HC, 16 Sep 2022) allow ECRL for the tax component; Flipkart (Patna HC, 2023) requires cash; SC batch pending [Unverified as at date] | Reword as contested with both lines; penalty component cash only (s.49(4)); mark `[VERIFY CURRENT POSITION]` |
| T-3 | s.15(3)(b) post-supply discount test stale from 01 Nov 2026 | Medium | `gst_authorities.py:299-304`, `gst_defects.py:185-187, 300-303` | Finance Act 2026 s.153 substitutes s.15(3)(b) (credit note + recipient ITC reversal under s.34), in force 01 Nov 2026 [Verified by delegate via secondary source; confirm against the Gazette] | Make the proposition period-dependent; add the FA 2026 position |
| T-4 | 57th GST Council (08 Oct 2026) recommendations on s.73/74/74A not surfaced | Medium | `calculators.py:302, 365-366, 454-458` | Recommended, not yet enacted: ₹10,000 SCN floor, removal of ₹10,000 minimum penalty, 5 % post-order concession; CBIC instruction already bars sub-₹10,000 SCNs [Unverified — confirm the instruction number] | Add a dated caveat; make stage constants notification-dated |
| T-5 | Grounding briefing discarded on substring match of the no-change marker | Medium | `grounding.py:134` `NO_CHANGE.lower() not in content.lower()` | A briefing that says "no material change to X, but note Y" is dropped entirely | Treat as no-change only when stripped content equals or starts with the marker and is short |
| T-6 | Citation verification silently truncates at 25 authorities | Medium | `verification.py:37,128` `authorities[:MAX_AUTHORITIES]`, no warning; `export.py:342-352` withholds unchecked authorities without stating why | Reviewer cannot see what was never checked | Emit dropped count as a blocker in the summary and reply pack |
| T-7 | Interest limb defaults to AGREED_PAID | Medium | `gst_defects.py:534` (`:505` late fee) | s.50(3) availed-not-utilised = nil; Rule 88B(1) proviso (Notif 12/2024-CT, 10 Jul 2024) | Default UNDECIDED where an ITC limb or s.50(3) is present |
| T-8 | Reconciliation takes `abs()` of difference | Low | `reconciliation.py:438-444` | Rows where 2A/2B > 3B are credit not availed, not exposure | Separate bucket "credit available, not availed"; exclude from contested total |
| T-9 | Authority citations with doubtful reporters | Low | `gst_authorities.py:201` Arise India "2018 (9) TMI 1461" (judgment is On Quest Merchandising, Del HC 26 Oct 2017; Arise India a co-petitioner); `:182,170,192` SCC OnLine numbers for D.Y. Beathel, Suncraft, LGW [Unverified]; LGW proposition overstated | — | Recast Arise India; add SLP-dismissal to Suncraft (14 Dec 2023); narrow LGW to its remand holding; mark unverified reporter numbers |
| T-10 | Minor: DRC-07 statute omits s.74A; `is_scn` misses "DRC01"; condonable-period and day-count conventions not printed in `basis` | Low | `gst.py:107`, `calculators.py:1146, 830, 855, 98` | — | Add s.74A; normalise hyphen; print conventions |

Confirmed correct by the delegate (no action): s.50(1)/(3) 18 % with FA 2022 s.116 retrospective; Rule 88B; s.73/74/74A stage percentages and windows; s.107(6)(b) and s.112(8)(b) 10 % with ₹20 crore CGST / ₹40 crore IGST caps w.e.f. 01 Nov 2024; FA 2025 penalty-only 10 % proviso from 01 Oct 2025; calendar-month limitation via GCA s.3(35); s.128A windows (tax by 31 Mar 2025, SPL by 30 Jun 2025); s.16(5)/(6); Rule 36(4); s.129(1) 200 % from 01 Jan 2022; GSTAT cohort dates.

### 3.3 Security, reliability, governance (delegated review, spot-checked)

| ID | Title | Sev | Evidence | Recommendation |
|---|---|---|---|---|
| S-1 | Authentication fails open when `users.json` is unreadable and no `APP_ACCESS_TOKEN` is set | High (Medium on Render where the token is auto-generated) | `auth.py:48-55` returns `True` (auth disabled) on any exception; `users.py:120-122` swallows `JSONDecodeError`/`OSError` and returns an empty store, so `user_count()==0` → anonymous partner | Require explicit `AUTH_DISABLED=true` for anonymous mode; raise on store read failure; return 503, never open |
| S-2 | Login lockout keyed on `request.client.host` behind Render's proxy | High | `main.py:224`; `users.py:304-308, 374-376`; uvicorn started without `--proxy-headers --forwarded-allow-ips` (`Dockerfile:50`) so every request shares one IP → one wrong password locks the whole firm out for 15 min | Pass forwarded headers; make the client key a throttle not a hard lock |
| S-3 | Shared `APP_ACCESS_TOKEN` always provisioned, grants non-attributable partner rights | Medium | `render.yaml:18-19` `generateValue: true`; `auth.py:20-27` legacy user role partner; `Login.jsx:93-116` | Opt-in only; log every use; disable from Admin |
| S-4 | No audit trail; all logging is `print()` | Medium | `main.py:44,503,545,676,960`; no record of export, delete, user CRUD, token use | JSON-lines audit log under `STATE_DIR` (user, action, matter, outcome, IP); ISO 27001 A.8.15 |
| S-5 | No per-matter authorisation | Medium | `main.py:336-375` all matters visible to any authenticated user incl. staff | Assignment field; staff see assigned matters only (A.5.15) |
| S-6 | Event loop blocked by PBKDF2 600k rounds and whole-file JSON re-parse per request | Medium | `main.py:216-226` sync `users.authenticate`; `users.py:131-133, 414-426` | `asyncio.to_thread`; cache store on mtime; or SQLite |
| S-7 | `users.json` read-modify-write without a lock | Medium | `users.py:370-410` and siblings | Process lock around load→mutate→save |
| S-8 | Export 500s on non-latin-1 client names | Medium | `main.py:449` filename header; Starlette encodes latin-1 | ASCII-fold plus RFC 5987 `filename*` |
| S-9 | Container runs as root; base images and uv unpinned; CI not `--frozen`; no vuln scan | Medium | `Dockerfile:10-11`, no `USER`; `test.yml:38` | `USER app`; digest pins; `uv sync --frozen`; `pip-audit`, `npm audit`, gitleaks |
| S-10 | Bootstrap password printed to platform logs | Medium | `users.py:452-457` | Force password change on first login; never print |
| S-11 | No security headers; 72 h bearer token in localStorage, no idle expiry | Medium | `api.js:21-30`; no CSP/HSTS anywhere | Header middleware; ≤12 h sliding expiry |
| S-12 | CORS defaults include localhost in production; wildcard `*.vercel.app` with credentials | Low | `config.py:92-95`; `main.py:54-56` | Empty default; scoped regex |
| S-13 | `/api/health` exposes model roster, ZDR flag and paths to staff; `/readyz` unauthenticated reveals key presence | Low | `main.py:173-180, 269-303` | Admin-only for detail |
| S-14 | General-council routes not gated server-side when flag is off; staff can run paid panels | Low | `main.py:842-970, 614-617` | 404 when disabled; `run_panel` permission or spend cap |
| S-15 | Exception text echoed to SSE clients | Low | `main.py:677, 961` | Generic message + correlation id |
| G-1 | Repository governance | Low | No tags/releases, 17 merged `claude/*` branches undeleted, no CODEOWNERS, SECURITY.md, CHANGELOG; repo description stale; branch protection status unknown (401 unauthenticated) | Tag `v0.2.0`; delete merged branches; add SECURITY.md with disclosure contact; enable branch protection requiring the `tests` check; fix description |
| G-2 | Documentation drift | Low | README says uploads are "never written to disk" (contradicted by multipart spooling); HANDOVER.md marked historical but still first-linked from CLAUDE.md; CLAUDE.md is 467 lines of agent instructions committed as product documentation | One current ARCHITECTURE.md; keep agent instructions separate and short |

### 3.4 What is done well (keep these)

- Design principles are enforced in code, not prose: Draft-tier leak audit aborts the run; unknown tier fails to the anonymising tier; only VERIFIED authorities reach the filing document; checker failure resolves to UNVERIFIED.
- Statutory arithmetic (s.50(3) tri-state, s.74A routing, per-Act pre-deposit caps, calendar-month limitation) is better than most firm spreadsheets and prints its working.
- Provenance model: every extracted field carries a source and a snippet; OCR-derived fields are visibly amber all the way to the defect list.
- Test discipline: 1,009 tests, golden set of nine notice forms, CI runs the OCR path with `OCR_REQUIRED=1` so a broken engine fails rather than skips.
- Security basics: 256-bit session tokens stored hashed, PBKDF2-HMAC-SHA256 600k rounds with transparent rehash, `compare_digest`, atomic 0600 writes, storage IDs validated by regex.

---

## 4. OCR improvement specification

Objective: a partner's assistant can photograph or scan any notice — PDF, image set, mixed digital/scanned, rotated, bilingual — and within a visible progress bar get a proposal whose every machine-read figure is traceable to the page image, correctable in place, and never silently lost. Nothing leaves the machine (principle retained).

### Phase 1 — Correctness and survival on 512 MB (1-2 weeks; fixes O-1, O-2, O-3, O-6, O-10)

1. Streaming page pipeline. `ocr.iter_pages(content)` yields `(page_no, bitmap)` one at a time; `ocr_pdf` consumes and discards. Peak memory target: ≤ 60 MB above baseline for any document. Acceptance: 40-page synthetic scan at 300 DPI, `tracemalloc` peak < 100 MB.
2. Per-page source decision. For each PDF page: take the text layer; if `< 80` chars after `_tidy`, OCR that page. Each page record: `{page, source: "text-layer"|"ocr", text, confidence}`. Document `source` becomes `"text-layer"`, `"ocr"` or `"mixed"`. Warnings list the scanned page numbers. Acceptance: mixed fixture recovers `2,80,470` with `source="mixed"` and an explicit warning; existing golden set unchanged.
3. Image intake. `SUPPORTED` adds `.jpg .jpeg .png .tif .tiff .webp .heic`; `pillow-heif` in the `ocr` extra. Images become a one-page-per-image document; multiple images in one upload are one document ordered by filename, then EXIF `DateTimeOriginal`. Frontend `accept` list updated; `capture="environment"` offered on mobile so a phone camera can be used directly. Magic-byte check on every upload before parsing.
4. Off the event loop. `read_notice_set` runs `extract_document` via `asyncio.to_thread`; a module-level semaphore (1 on Starter) serialises OCR jobs so two uploads cannot double memory. `OMP_NUM_THREADS`/`onnxruntime` intra-op threads set from `os.cpu_count()`.
5. Constants scale with DPI (`_ROW_TOLERANCE`), default `OCR_MAX_PAGES` to 20 with the truncation warning offering "Read pages 21-40" as a second request.

### Phase 2 — Reviewer experience (2-3 weeks; fixes O-5, O-7, O-8, O-11)

6. Asynchronous job with progress. `POST /api/panel/extract` returns `{job_id}` immediately; `GET /api/panel/extract/{job_id}/events` streams SSE `{stage: "render"|"ocr"|"fields", page, of, elapsed}`; final event carries the proposal. UI shows "Reading page 7 of 23 — about 40 s left" and a cancel button. Removes dependence on the proxy timeout.
7. "Text as read" panel. Per-page tabs; scanned pages amber; doubtful lines highlighted with confidence; text editable; "Re-read fields" re-runs local extraction only (no model). Field snippets link to page and line.
8. Orientation detection. Before recognition, use pdfium `/Rotate`; if absent, run detection on a downscaled page, compute dominant box orientation, rotate 90/270 as needed, recognise once. Fixture: 90° and 270° pages.
9. Figure cross-check. For each annexure row read from a scan, `notice_tables` already validates the row against its printed total; surface the result per row (✓ row sums / ✗ does not sum) in the defect list so the reviewer checks the ✗ rows first.

### Phase 3 — Indian notices as they actually arrive (4-6 weeks; fixes O-4, O-9)

10. Script coverage. Detect unrecognised text regions (detection boxes with empty recognition or coverage gap) and warn by script. Add optional language models on the same ONNX runtime (Devanagari, Tamil, Telugu, Kannada, Gujarati, Malayalam, Bengali) selected from the matter State, downloaded to `STATE_DIR/models` on first use (still local).
11. Real-scan corpus. Build `evals/scans/` from anonymised real notices (identifiers redacted on the image, not just the text) across at least six States; add a scorer for field recall and figure exactness per scan class; gate changes to `ocr.py` on it the way `test_golden_set.py` gates segmentation.
12. Pre-processing only if the corpus shows benefit: deskew, adaptive threshold, shadow removal for phone photos.

### Acceptance criteria for the whole spec

- No synthetic or corpus document exceeds 100 MB peak above baseline.
- A 20-page scan shows progress within 2 s of upload and never blocks a concurrent request for more than 100 ms.
- Every OCR-read figure in the proposal is reachable from a page image in two clicks, and every doubtful line is visible without opening the PDF.
- Mixed, rotated and image-set notices produce the same proposal as their clean-PDF equivalents on the golden set.
- A notice containing non-Latin text produces an explicit script warning rather than a silent omission.

---

## 5. Recommended sequence

| Order | Items | Effort | Rationale |
|---|---|---|---|
| 1 | O-1, O-2, T-1, S-1, S-2 | 3-5 days | Availability, silent figure loss, overstated penalty base, auth fail-open, firm-wide lockout — all plausible this week on live notices |
| 2 | O-3, O-7, O-8, T-2, T-5, T-6, S-8 | 1-2 weeks | Owner's usability pain; reviewer confidence; filing accuracy |
| 3 | Phase 2 async job and progress; S-3 to S-7, S-9 to S-11 | 2-3 weeks | Operate like a product, not a script; ISO 27001 / SOC 2 readiness |
| 4 | Phase 3; T-3, T-4, T-7 to T-10; G-1, G-2 | Ongoing | Coverage and currency |

---

## 6. Items not verified

- Render Starter CPU allocation and the proxy idle-response timeout (~100 s) — confirm in Render documentation; the Phase 2 design removes the dependency either way.
- Branch protection on `master` (API returned 401 unauthenticated).
- Finance Act 2026 s.153 commencement notification text; 57th Council follow-through and the CBIC instruction number on sub-₹10,000 SCNs.
- Reporter citations: SCC OnLine numbers for Suncraft, D.Y. Beathel, LGW; TMI number for Arise India; Gaurav Jain neutral citation and date; "GSTAT Hyderabad to the same effect".
- Supreme Court outcome on s.168A notifications 09/2023 and 56/2023.
- Behaviour on a real Render instance under a 40-page scan (measured locally only; OOM is an inference from 1,097 MB peak vs 512 MB).

---

## 7. Verification performed by the reviewer

- Cloned `55584f4`; installed with `uv sync --extra ocr` (Python 3.12.16, rapidocr-onnxruntime 1.4.4, pypdfium2 5.12.1, onnxruntime 1.19.2).
- `OCR_REQUIRED=1 uv run pytest -q`: 1,009 passed, 1 skipped.
- Eight OCR probes through the production `intake.extract_document` path; results quoted in §3.1 are measured, not estimated.
- Every delegated High and Medium finding spot-checked against the cited source lines (`auth.py:48-55`, `users.py:120-122`, `calculators.py:1121-1134`, `grounding.py:134`, `verification.py:37,128`).

Reviewer: Hermes Agent for CA Loganathan Anandan. For the owner's sign-off; not for distribution to clients.
