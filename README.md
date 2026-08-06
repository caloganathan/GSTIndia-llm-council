# Compliance Panel — GST advisory, plus the general LLM Council

![llmcouncil](header.jpg)

> **Built on [Andrej Karpathy's LLM Council](https://github.com/karpathy/llm-council).**
> The multi-model deliberation approach — parallel responses, anonymised peer
> review, synthesis by a chairman — was conceived and published by
> [Andrej Karpathy](https://github.com/karpathy). This repository extends that idea
> into a domain-specific compliance tool for Indian tax practice.
>
> **Extended and maintained by [CA Loganathan Anandan](https://www.linkedin.com/in/caloganathan)**,
> Chartered Accountant — India, Indonesia & Singapore.
> Repository: [GSTIndia-llm-council](https://github.com/caloganathan/GSTIndia-llm-council)

Two modes in one application:

**Compliance Panel** — an adversarial panel for Indian GST notice work. Four
counsel argue the matter, cross-examine each other, and a chairman determines
the firm's position. Every authority cited is then checked against live
sources and labelled VERIFIED / UNVERIFIED / NOT FOUND before a partner ever
sees it. Output is a reply pack: draft reply, issue-wise analysis, authorities
table, risk flags, board summary, and a working note for the file.

**General Council** — the original multi-model council, for open research
questions rather than a specific notice.

## What this actually does — a handover note for smaller practices

If you're forking this to run in your own firm, here is the plain-language
version to pass to whoever will actually use it day to day.

**What it's for.** You upload a GST notice. Four AI "counsel" argue it from
different angles — the department's case, the assessee's case, procedure and
limitation, and risk and ethics — then a "chairman" decides the firm's
position and drafts a reply. Every case citation in that draft is checked
against current sources before anyone sees it, and marked Verified /
Superseded / To be confirmed rather than trusted blindly. If you also have a
2A/2B-vs-3B reconciliation working, upload the Excel — the ITC mismatch is
auto-sorted into categories (timing, RCM, import IGST, non-filing supplier,
genuinely ineligible, etc.) and the draft reply addresses each category with
its own figures, instead of arguing one lump-sum number.

**What it produces.** A Word document formatted like a normal firm output —
Arial, monochrome, bold headings, nothing that reads as machine-generated —
containing the draft reply, an issue-wise analysis, a schedule of
authorities, risk flags for a reviewing partner, and a note for the file.

**Two tiers, and why.** *Draft* strips the client's name, GSTIN and PAN before
anything leaves the machine, and restores them locally afterwards — good for a
first read or a second opinion. It exports, but every page is watermarked
**not for filing**, so a draft cannot be mistaken for the real thing.
*Pro* sends full facts through zero-retention routing and exports unwatermarked
— use this for anything actually going to the department.

**Instructions to hand to your team:**

1. Log in with the credentials you were given.
2. New Matter → upload the notice (and the reconciliation Excel, if you have
   one). Scanned notices are read too, if the OCR extra is installed — see
   "Scanned notices" below.
3. Check the auto-extracted facts (GSTIN, dates, amounts, section) — correct
   anything wrong before running the panel. **Each field shows the sentence it
   was read from**, so you can confirm it without opening the PDF. Anything
   read from a scan is marked in amber: check every one of those figures.
4. Choose Draft (quick check) or Pro (real work) and run it. The estimated
   cost in rupees is shown before you start.
5. Read all four counsel opinions and the chairman's determination. **This is
   a draft for professional review, not a filing.** Any citation marked "to be
   confirmed" or "not traced" must be checked against the reported text before
   it goes anywhere near a signature.
6. Edit as needed, export to Word, and route it through the firm's normal
   sign-off — a partner reads and signs every output, same as a junior's
   draft today.

**The one honest caveat to give them up front:** this is new and still being
validated notice by notice. Treat its output as a strong first draft from a
very well-read junior — not a substitute for the partner's judgment.

### Reply deadlines

The dashboard opens on what needs attention: matters past their reply date
first, then those due within the week. **Add to calendar** downloads every
reply date as an `.ics` file that Outlook, Google Calendar and Apple Calendar
all open, with a reminder two days out — two rather than one, because a reply
needs the client's documents and a reminder the day before arrives too late to
ask for anything.

This is here because a missed reply date is the most expensive ordinary
mistake in GST practice. The window closes, an ex-parte order follows under
s.73(9) for the full amount proposed, and what was a reply becomes an appeal
with a 10% pre-deposit and a limitation clock of its own.

### Scanned notices

Notices that arrive as images — printed, signed, stamped, scanned — need the
optional OCR engine:

```bash
uv sync --extra ocr
```

It runs entirely on your machine. Cloud OCR was deliberately not used: a page
image cannot be anonymised before it is uploaded, so it would break the Draft
tier's promise that client identifiers never leave the building. Without the
extra installed the application says so plainly and asks you to paste the text
— it never guesses.

Everything read from a scan is machine-read and marked as such, all the way
through to the review screen. **Check every figure against the notice before
running the panel.**

## The Compliance Panel

### Why the counsel are organised this way

A notice usually concerns one law, so a panel of "GST specialist / income tax
specialist / FEMA specialist" produces one real opinion and three empty ones.
This panel is organised by **role in the argument**, which is how a technical
clearance actually runs in a professional firm:

| Counsel | Brief |
|---|---|
| **Revenue's Advocate** | Argues the department's case at its highest, so weaknesses surface internally rather than across the table |
| **Assessee's Advocate** | The positive case on merits, grading each argument STRONG / DEFENSIBLE / WEAK |
| **Procedural Counsel** | Limitation, jurisdiction, natural justice, defects in the notice — where matters are more often won |
| **Risk & Ethics Counsel** | Penalty exposure, aggressiveness of the position, cross-State consistency, amnesty arithmetic, file documentation |
| **Chairman** | Decides. Resolves the disagreements explicitly rather than averaging them |

Stage 2 is **cross-examination**, not ranking: each counsel attacks the others'
reasoning, flags citations it doubts, and concedes where it has been beaten.

### Jurisdiction awareness

A Karnataka High Court ruling binds a Karnataka officer; a contrary Madras
ruling does not. The intake captures the State, and the prompts weight binding
against persuasive precedent accordingly — which is exactly what a group
operating across several registrations needs, and what generic tools ignore.

### Reading the notice

Upload the notice as PDF, Word or text. Most of the intake form is filled
**without a model at all** — GSTIN, entity name, notice type, reference
number, dates, amounts, section invoked and tax period are read locally by
pattern, and the State is derived from the first two digits of the GSTIN,
which is what drives the jurisdiction weighting.

A model reads only the two fields a pattern cannot: what the issues are and a
summary of the facts. On the Draft tier the notice text is scrubbed first, so
an uploaded notice is no less private than a typed one. The uploaded file is
parsed in memory and never written to disk.

Everything extracted is a **proposal**, shown with its source, for the user to
correct before the panel runs. Scanned notices with no text layer are read by
the optional local OCR engine (see "Scanned notices" above) and everything it
reads is marked as machine-read all the way to the review screen. Without that
extra installed the application says so plainly and asks for the text — it
never guesses, because a wrong OCR read is worse than an empty field.

### Reconciliation ingestion (2A/2B vs 3B)

ITC-mismatch notices are answered with numbers, not just argument, and the
architecture reflects one hard constraint: **the reconciliation rows never
reach a model.** A real working is thousands of invoice lines — on the order
of 500,000 tokens — and it is third-party supplier data the client has no
business disclosing to an external API. Bucketing the mismatch is
deterministic arithmetic, so it happens locally in Python. Only the
aggregate — bucket, count, amount, share of the total, legal position — is
put in front of the panel: a few hundred tokens, regardless of whether the
sheet has twenty rows or twenty thousand.

Upload the xlsx/csv on the intake screen; columns are detected by alias
(supplier GSTIN, invoice details, book vs portal amounts, remarks) and each
row is classified into one of nine buckets:

| Strength | Buckets | Meaning |
|---|---|---|
| Strong | RCM, import IGST, ISD, timing | Excluded at the threshold, or a timing difference — not a real mismatch |
| Defensible | Amendment, supplier error, clerical | Explicable, needs documentation |
| Weak | Non-filer | The genuine section 16(2)(c) exposure |
| Concede | Ineligible | No credible argument — say so |

`Unreconciled` is a separate, deliberately blunt category for whatever
doesn't sort cleanly — it is never folded into a benign bucket. Supplier
GSTINs are masked on the anonymising tier, since they belong to a third
party, not the client. The chairman is instructed to meet the difference
category by category with the figures, never as a single undifferentiated
number.

### Citation verification

The most dangerous failure mode is a fabricated authority reaching a signing
partner. Every citation — from the authorities table *and* from the body of
the draft reply — is extracted and checked for three things: does it exist,
does it support the proposition, and **is it still good law**. That third
check catches the quiet failure: a circular withdrawn last quarter reads
exactly like sound authority.

| Status | Meaning |
|---|---|
| VERIFIED | Traced, supports the proposition, and appears current |
| SUPERSEDED | Exists but amended, withdrawn, overruled or stayed |
| UNVERIFIED | Could not be confirmed |
| NOT_FOUND | Could not be located — treat as fabricated |

Nothing is ever silently upgraded: if the checker fails, returns nonsense, or
the panel itself flagged a citation as uncertain, the result is UNVERIFIED.

**Be clear about what this is.** Verification searches public sources on the
open web. It is not a licensed citator such as Taxmann or Manupatra, and it
will miss things a citator catches. It is a safety net against fabrication and
obvious staleness, not a substitute for reading the authority. The UI and the
reply pack both say so.

### Two tiers — a risk tier, not just a price tier

| | Draft Council | Pro Council |
|---|---|---|
| Models | Cheap paid endpoints — cents per run | GPT-5.5, Claude Opus 4.8, Gemini 3.1 Pro, Grok 4.3 |
| Client identifiers | **Stripped before any request leaves the machine** | Full facts, zero-data-retention routing |
| Output | Every exported page watermarked, not for filing | Signing-ready pack with DOCX export |

On the Draft tier anonymisation is enforced in code and the run **aborts** if
any identifier survives the scrub. Identifiers are restored locally afterwards,
so the partner still reads real names while the model never saw them.

Export is allowed on both tiers, and that is deliberate: blocking it on the
cheap tier only pushed people into copying text out of the browser, which loses
the watermark along with it. The Draft tier stamps every page instead.

**There was once a genuinely free tier**, running on OpenRouter's `:free`
endpoints. Every model ID in it went stale and the whole tier failed silently
in production — including notice reading, because the reader borrows the tier's
grounding model. Free endpoints churn faster than a professional tool can
track. The replacement is a cheap *paid* tier: a full run costs cents, the IDs
are stable, and the property that actually mattered is unchanged. Matters saved
under the old tier open on Draft, never on Pro — re-running work someone chose
to anonymise must not silently send real identifiers.

### Statutory computations — Python, never a prompt

Interest under s.50, the s.73/74 penalty stages, the s.107/112 pre-deposit,
appeal limitation and s.128A eligibility are computed in code and never by a
model. A model that computes 18% for 402 days on Rs. 3,17,450 produces a figure
that looks right, cannot be audited, and is different next run. Every figure
here carries its own working — the period, the rate, the day count — so it can
be checked line by line by whoever signs it.

Two of these are worth calling out because they are routinely conceded in
practice for want of a computation:

- **s.50(3) at 24% applies only to credit wrongly availed AND utilised.**
  Availed but not utilised puts the matter outside s.50(3) altogether. That is
  a ground of defence, not merely a lower rate, and the output says so.
- **The s.73 and s.74 concession windows are date-driven**, and the dates are
  not in the notice — they are computed from it. Under s.73, tax and interest
  paid within 30 days of the SCN attracts **no penalty at all**.

These reach the internal file note. They reach the filing document only where
the posture is one that pays, because a penalty computation put in front of the
officer volunteers an admission nobody asked for.

### Personal hearing brief

The file note carries a brief for whoever attends the s.75(4) hearing: for each
limb, the position in one line, the artefact to carry, and the questions
officers actually put on that defect type. The hearing is where small-practice
representation is weakest — not because the law is unknown, but because the
questions are not anticipated and a limb answered perfectly on paper gets
conceded across the table.

### What a run costs

Shown in rupees, before the run and after it. The estimate is built from your
own completed matters rather than a published price table — a table keyed to
model IDs goes stale silently, which is exactly how the old free tier failed.
Until you have run a few matters it says so and quotes a wide range.

It prices the limbs that **convene counsel**, not the total. Triage means most
limbs are answered by arithmetic, documents or a payment: on the reference
eight-limb notice, four.

### Users and roles

| Role | Sees |
|---|---|
| **Partner** | Everything, plus administration and user management |
| **Manager** | Full deliberation and export |
| **Staff** | Determination and verification trail only — not the counsel arguments |

On first run the server creates a partner account and prints the credentials
to its console. If that log has scrolled away, or the account needs to change,
use the admin CLI — it operates directly on the persisted user store, so it
works against a live deployment as well as locally:

```bash
python -m backend.cli create-admin --email you@firm.in --password ...   # or omit --password to be prompted
python -m backend.cli reset-password --email you@firm.in --password ...
python -m backend.cli set-role --email someone@firm.in --role manager
python -m backend.cli list-users
```

On Render, run this from the service's **Shell** tab so it operates on the
mounted volume the running app reads. In the meantime, the shared
`APP_ACCESS_TOKEN` (Environment tab → reveal the auto-generated value) always
works as a full partner login via *"Use a shared access token instead"* on the
login screen — the fastest way in if you're locked out right now.

### The reply pack

The export is a professional work product, formatted the way a tax practice in
India formats a file that goes to a partner and then to the department: Arial
11pt, black on white, bold headings and no other ornament. Sections run
Position Recommended, Issues and Position Taken, Draft Reply, Schedule of
Authorities, Points for Reviewer Attention, Documents to be Placed on Record,
Note for the File, Summary for the Board.

The draft reply is written to be lifted onto letterhead: numbered paragraphs,
preliminary and jurisdictional objections taken first, merits advanced without
prejudice, closing prayer. Formal Indian professional register throughout.

Nothing in the deliverable discloses the machinery behind it. The pack is the
firm's work product, settled and signed by a member — how it was prepared is
internal, exactly as a junior's draft carries the partner's name and not the
junior's. Set `EXPORT_PROVENANCE=true` to append an internal annexure for the
firm's own file; the complete record is retained in the matter regardless.

What the export does carry is a standing note in the register a manager uses
when passing a file up: the draft is for the engagement partner to settle and
sign, and authorities shown as *To be confirmed* or *Not traced* in the
Schedule of Authorities are to be verified against the reported text before
filing. That is a working-paper control, and it stays.

## General Council — the heritage mode

**Off by default.** Set `ENABLE_GENERAL_COUNCIL=true` to show it. It is the
upstream project this one grew out of, it still works, and no client
engagement uses it — left visible it doubles the navigation a new user has to
understand and invites the question "so is this a chatbot?".

Instead of asking a question to a single LLM provider, group the frontier models into your "LLM Council". This web app looks like ChatGPT except it uses OpenRouter to send your query to multiple LLMs, asks them to review and rank each other's work (anonymized, and never their own), and finally a Chairman LLM produces the final response.

What happens when you submit a query:

1. **Stage 1: First opinions**. The query — along with the conversation history — is given to all council LLMs individually, and the responses are collected and shown in a tab view. Optionally, models can ground their answers with live **web search**.
2. **Stage 2: Peer review**. Each LLM is given the *other* models' responses, anonymized as "Response A/B/C" so it can't play favorites — and it never sees its own response, so it can't vote for itself. Each reviewer evaluates accuracy, depth, and usefulness, and produces a ranking. Rankings are aggregated with position normalization.
3. **Stage 3: Final response**. The Chairman receives all responses, all reviews, the label→model mapping, and the peer-review consensus, and synthesizes the final answer.

A per-message **Quick mode** skips Stage 2 for faster, cheaper answers (individual responses + synthesis only). Every exchange reports its **token usage and dollar cost**.

## Features

### Compliance Panel

- Defect-wise intake: a notice is segmented into its limbs, each with the
  department's own heading and head-wise figures, and answered one at a time
- Four adversarial counsel plus a chairman, organised by role in the argument
- Every citation checked against live sources; nothing unverified reaches the
  filing document
- Two documents, never merged: the filing reply and the internal file note
- Statutory arithmetic in Python — s.50 interest, the s.73/74/74A penalty
  stages with their concession deadlines, s.107/112 pre-deposit, appeal
  limitation in calendar months, s.128A eligibility — each carrying its working
- 2A/2B-vs-3B reconciliation bucketed locally; only the aggregate reaches a
  model, never the invoice rows
- Draft and Pro tiers as risk tiers, with enforced anonymisation on Draft
- Reply-deadline tracking with an iCalendar export
- Role-based access: partner / manager / staff

### General Council (heritage mode, off by default)

- Multi-turn conversations — the whole council sees the conversation history
- Self-vote-free anonymized peer review with normalized aggregate rankings
- Reasoning effort control (`REASONING_EFFORT=low|medium|high|none`)
- Optional web search grounding per message (OpenRouter web plugin)
- Full vs Quick deliberation modes per message
- Per-message cost and token accounting
- Retries with exponential backoff; per-model failures are surfaced in the UI instead of silently dropped
- Bearer-token auth for private cloud deployment; single-container packaging
- Atomic conversation storage; conversations are deletable from the sidebar

## Setup (local development)

The project uses [uv](https://docs.astral.sh/uv/) for Python and npm for the frontend.

```bash
uv sync
cd frontend && npm install && cd ..
```

Create a `.env` file in the project root (see `.env.example`):

```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

Get your API key at [openrouter.ai](https://openrouter.ai/) and make sure it has credits.

Run it:

```bash
./start.sh
# or manually:
# Terminal 1: uv run python -m backend.main       (API on :8001)
# Terminal 2: cd frontend && npm run dev           (UI on :5173)
```

Open http://localhost:5173. With no `APP_ACCESS_TOKEN` set, auth is disabled locally.

## Configuration

Everything is configurable via environment variables (or `.env`) — no code
edits needed. **[`.env.example`](.env.example) is the complete list**, grouped
and commented, and the values shown there are the real defaults. These six are
the ones a deployment must actually decide:

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required. Nothing runs without it. |
| `APP_ACCESS_TOKEN` | *(unset = auth off)* | Shared secret for the login screen. **Never deploy publicly without this or a user account.** |
| `STATE_DIR` | parent of `DATA_DIR` | Matters, user accounts and sessions. Must sit inside the mounted volume. |
| `DATA_DIR` | `data/conversations` | Conversation storage path. |
| `DEFAULT_PANEL_TIER` | `pro` | `draft` (anonymising) or `pro`. |
| `ENABLE_GENERAL_COUNCIL` | `false` | Show the heritage chat mode. |

Everything else — the per-seat model IDs for each tier, reasoning effort and
output ceilings per role, ZDR routing, OCR tuning, firm identity on the export,
upload limits, session lifetime — has a working default and is documented in
`.env.example`.

Configured model IDs, including each tier's grounding model, are validated
against OpenRouter's catalogue at startup; check the logs or `GET /api/health`
for warnings about stale IDs. **A stale grounding ID breaks notice reading**,
because the reader borrows it.

### Checking the model roster

Model IDs on OpenRouter churn, and a stale one fails at the moment you need it.
The doctor checks every slot against the live catalogue and proposes
replacements — run it before a deploy rather than discovering the problem after
one:

```bash
python -m backend.cli check-models            # what is stale
python -m backend.cli check-models --suggest  # and what to put in its place
```

It needs outbound access to `openrouter.ai` and no API key. Run it locally, or
from the Render service's **Shell** tab, where it also picks up the live
configuration.

It checks more than existence, because the slots are not interchangeable: the
verifier and grounding slots need room for injected search results on top of
their prompt, the chairman writes the longest output in the product against a
16,000-token ceiling, and a draft-tier seat that is not materially cheaper than
Pro defeats the point of having two tiers. Suggestions prefer the same vendor
as the stale ID, so fixing a typo does not quietly reshuffle which model argues
which side — and they are candidates, not decisions. `--suggest` prints
paste-ready environment variables; **every model is env-overridable, so a
stale roster is fixed without a code change.**

## Running with Docker

```bash
cp .env.example .env   # fill in OPENROUTER_API_KEY (and APP_ACCESS_TOKEN if exposed)
docker compose up --build
```

Open http://localhost:8001 — the container serves both API and UI, and conversation data persists in a named volume.

## Deploying to Render (private cloud)

The repo includes `render.yaml`:

1. Push this repository to your GitHub account.
2. In the [Render dashboard](https://dashboard.render.com/): **New → Blueprint**, select the repo. Render reads `render.yaml` and provisions a Docker web service with a 1 GB persistent disk mounted at `/app/data`.
3. Set `OPENROUTER_API_KEY` when prompted (it's marked `sync: false` so it never lives in the repo).
4. `APP_ACCESS_TOKEN` is auto-generated by Render — copy it from the service's Environment tab. This is the token you'll enter on the login screen.
5. Deploy. Your council is at `https://<service-name>.onrender.com`, protected by the access token, with HTTPS handled by Render.

Any other Docker host (Fly.io, Railway, a VPS) works the same way: build the image, mount a volume at `/app/data`, and set the secrets.

**Do not deploy publicly without `APP_ACCESS_TOKEN` set** — otherwise anyone who finds the URL can spend your OpenRouter credits and read your matters.

### Start commands

The ASGI application is exported from `main.py` at the repository root, so
every conventional entrypoint resolves:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001     # container CMD and Procfile
gunicorn -k uvicorn.workers.UvicornWorker main:app
python main.py
python -m backend.main
```

Platforms that auto-detect a Python web service look for a top-level `app` in
`main.py`. `backend/main.py` uses relative imports and cannot be loaded
directly as a script — the root module imports it as part of the package and
re-exports the instance.

### Persistence

Two paths, both of which must sit inside the mounted volume:

| Variable | Holds | Container value |
|---|---|---|
| `DATA_DIR` | Conversations | `/app/data/conversations` |
| `STATE_DIR` | Matters, user accounts, sessions | `/app/data` |

`STATE_DIR` defaults to the parent of `DATA_DIR` when `DATA_DIR` ends in
`conversations`, and to `DATA_DIR` itself otherwise. Set it explicitly in
production. A deployment that writes user accounts outside the volume loses
every account on redeploy, which is why both are stated in `render.yaml`
rather than inferred.

### Deploying the frontend separately (Vercel, Netlify, Cloudflare Pages)

The API is a stateful, long-running service: it writes conversations, matters
and user accounts to disk, and a full panel run takes two to four minutes.
**Serverless platforms cannot host it** — their filesystems are ephemeral, so
every account and matter would be lost between invocations, and function
timeouts cut a deliberation off mid-run. Keep the API on a container host with
a persistent disk.

The frontend is a static bundle and can be served from anywhere. To split it
out, build with the API's public URL baked in:

```bash
VITE_API_BASE_URL=https://your-api.onrender.com npm run build
```

On Vercel, set `VITE_API_BASE_URL` as an environment variable — `vercel.json`
already points the build at `frontend/` and rewrites unknown paths to
`index.html` for client-side routing.

Then let the API accept that origin:

```bash
CORS_ORIGINS=https://council.vercel.app,https://council.yourfirm.in
CORS_ALLOW_VERCEL_PREVIEWS=true    # optional: accept *.vercel.app preview URLs
```

Leave both unset for the single-service deployment, where the bundle is
same-origin and CORS never applies.

### Health and readiness

| Endpoint | Purpose |
|---|---|
| `/healthz` | Liveness. The process is up. Use this for the platform health check. |
| `/readyz` | Readiness. Reports whether the API key is configured, state is writable, the frontend bundle is present, and auth is enabled. |

`/readyz` returns `degraded` rather than failing when something is
misconfigured — check it first if a deployment comes up but does not work.
Startup never aborts on a failed optional step: a service that refuses to
start because the model catalogue was briefly unreachable is worse than one
that starts and reports the problem.

## Tests

```bash
uv run pytest
```

The suites that matter most: the sanitizer (identifier leaks —
a failure there is a confidentiality breach, not a bug), citation verification
and its never-upgrade rule, reply-pack formatting (Arial-only, monochrome-only,
no machine vocabulary in the deliverable), reconciliation ingestion (proof
that no invoice-level data ever reaches a model, and that briefing size is
independent of row count), and deployment invariants (the root `app` export,
and state paths that can never resolve outside the volume).

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter API
- **Frontend:** React + Vite, react-markdown for rendering
- **Reconciliation:** openpyxl for xlsx, csv.Sniffer for delimiter detection — parsed in memory, never written to disk
- **Storage:** JSON files, atomic writes — conversations in `DATA_DIR`, and
  matters, user accounts and sessions in `STATE_DIR`
- **Packaging:** uv for Python, npm for JavaScript, multi-stage Dockerfile

## Licence and attribution

The compliance layer — the panel, citation verification, anonymisation,
notice intake, reconciliation, the reply pack and the domain packs — is the
original work of CA Loganathan Anandan and is licensed under the
**[Apache License 2.0](LICENSE)**. Use it, modify it, run it in your firm,
build on it commercially. The conditions are the ordinary Apache ones: keep
the copyright notice, keep the [NOTICE](NOTICE) file, and state what you
changed.

**On the origin of this project.** It began from
[karpathy/llm-council](https://github.com/karpathy/llm-council), which carries
no licence file — its author released it stating it was "provided here as is
for other people's inspiration". Since no licence could be relied upon, the
inherited implementation has been rewritten: the transport layer, the storage
layer, the deliberation prompts and the request schema were each
reimplemented. What remains in common is function signatures, dictionary keys,
imports and framework idiom — the shape the libraries impose, not anyone's
authorship.

**The credit stands regardless, and it is not conditional on the code.** The
idea — several models answering, refereeing one another blind, and a chair
settling it — is Andrej Karpathy's. A rewrite changes whose lines are in the
file; it does not change whose insight started this. That acknowledgement stays
in [NOTICE](NOTICE) permanently, and it will travel to every further
application built on this foundation, whatever the law or the jurisdiction.
A weekend someone spent being generous is why this exists at all, and saying so
costs nothing worth keeping.

