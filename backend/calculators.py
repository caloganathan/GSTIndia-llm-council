"""Statutory arithmetic — interest, penalty, pre-deposit, amnesty eligibility.

WHY THIS IS PYTHON AND NOT A PROMPT
-----------------------------------
The same reason the reconciliation buckets are Python: it is arithmetic with a
statutory rule attached, and arithmetic is the one thing a language model has
no business doing in a document that goes to a tax officer. A model that
computes 18% for 402 days on Rs. 3,17,450 will produce a number that looks
right, cannot be audited, and will be different next run. Every function here
returns its own working — the periods, the rates, the day counts — so the
figure in the reply can be checked line by line by whoever signs it.

This also closes a real gap in practice. Interest and penalty are computed in
ad-hoc spreadsheets that are rebuilt per matter and per person, and the errors
are systematic: interest run to the notice date rather than the payment date,
s.50(3) applied where only s.50(1) is engaged, the 73(5) concession window
missed entirely because nobody checked the date against the calendar.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No rate is inferred and no window is guessed. Rates and windows are stated
constants with the notification behind them named, and where a value depends
on something this module cannot know — whether the credit was *utilised*, not
merely availed; whether the section-128A window is still open on the date of
filing — the function says so in `assumptions` and `caveats` rather than
choosing for the user. The panel's grounding stage checks the live position;
this module does the sums under the position it is given.

Everything returned is a WORKING, not an opinion. It reaches the file note by
default. It reaches the filing document only where the posture is one that
pays (`agreed_paid`, `partial`, `paid_under_protest`), because a figure quoted
to the department is an admission.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Interest — Section 50
# ---------------------------------------------------------------------------
# s.50(1): 18% per annum on tax not paid or short paid, from the day after the
#          due date of the return to the date of payment.
# s.50(3): 24% per annum, and after the Finance Act 2022 amendment (w.e.f.
#          1 July 2017, retrospectively) it applies ONLY to input tax credit
#          that was wrongly availed AND utilised. Availment alone, reversed
#          without utilisation, does not attract s.50(3) — the distinction is
#          worth real money and is routinely conceded by taxpayers who never
#          checked whether the credit was utilised at all.
INTEREST_RATE_NORMAL = 18.0
INTEREST_RATE_ITC_UTILISED = 24.0

# The proviso to s.50(1): where the return is filed after the due date, interest
# on the self-assessed liability runs only on the portion discharged in cash,
# not on the portion set off against credit in the electronic credit ledger.
# This is a live and frequently missed relief.
CASH_LEDGER_PROVISO = (
    "Proviso to Section 50(1): where the return for the period is furnished "
    "after the due date, interest is payable only on that portion of the "
    "liability discharged by debit to the electronic cash ledger. Confirm the "
    "cash/credit split before adopting the figure below, which is computed on "
    "the whole amount."
)

DAYS_IN_YEAR = 365


def _as_date(value: Any) -> Optional[date]:
    """Accept an ISO string, a date, or a datetime. Return None on anything else."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def compute_interest(
    amount: float,
    from_date: Any,
    to_date: Any,
    rate: float = INTEREST_RATE_NORMAL,
    basis: str = "Section 50(1)",
) -> Dict[str, Any]:
    """
    Simple interest for a single period, with its working.

    Day count is inclusive of the end date and exclusive of the start, which is
    how "from the day succeeding the due date until the date of payment" reads
    and how the portal computes it.

    Returns `computed: False` with a stated reason rather than a zero when the
    inputs do not support a computation. A zero is a figure; a refusal is a
    blank the reviewer can see, and this product does not fill blanks with
    zeros.
    """
    start, end = _as_date(from_date), _as_date(to_date)

    if start is None or end is None:
        return {
            "computed": False,
            "reason": "Both the due date and the date of payment are needed "
                      "before interest can be computed.",
            "amount": None,
        }
    if amount is None or amount <= 0:
        return {
            "computed": False,
            "reason": "No tax amount to compute interest on.",
            "amount": None,
        }
    if end <= start:
        return {
            "computed": False,
            "reason": f"The date of payment ({end.isoformat()}) is not after "
                      f"the due date ({start.isoformat()}), so no interest "
                      "arises on these dates. Check both before relying on this.",
            "amount": 0.0,
        }

    days = (end - start).days
    interest = amount * (rate / 100.0) * (days / DAYS_IN_YEAR)

    return {
        "computed": True,
        "amount": round(interest, 2),
        "principal": round(float(amount), 2),
        "rate": rate,
        "days": days,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "basis": basis,
        "working": (
            f"Rs. {amount:,.2f} x {rate}% x {days}/{DAYS_IN_YEAR} days "
            f"({start.strftime('%d.%m.%Y')} to {end.strftime('%d.%m.%Y')}) "
            f"= Rs. {interest:,.2f}"
        ),
    }


def interest_on_defect(
    amount: float,
    due_date: Any,
    payment_date: Any,
    itc_utilised: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Interest on one limb, choosing the rate the way the statute does.

    `itc_utilised` is tri-state on purpose. True means s.50(3) at 24%. False
    means credit availed but not utilised, where the amendment puts the matter
    outside s.50(3) altogether — that is a defence, and it is flagged as one.
    None means nobody has established which, and the working says so rather
    than defaulting to the rate that happens to be safer for the department.
    """
    if itc_utilised is True:
        result = compute_interest(amount, due_date, payment_date,
                                  INTEREST_RATE_ITC_UTILISED, "Section 50(3)")
        result["caveats"] = [
            "Section 50(3) is charged at 24% only where the credit was both "
            "wrongly availed AND utilised. Confirm utilisation from the "
            "electronic credit ledger before this figure is offered."
        ]
        return result

    result = compute_interest(amount, due_date, payment_date,
                              INTEREST_RATE_NORMAL, "Section 50(1)")
    caveats = [CASH_LEDGER_PROVISO]
    if itc_utilised is False:
        caveats.insert(0,
            "Credit availed but NOT utilised: following the retrospective "
            "amendment to Section 50(3) (Finance Act 2022, w.e.f. 01.07.2017), "
            "interest under Section 50(3) does not arise at all on these facts. "
            "This is a ground of defence, not merely a lower rate — take it as "
            "a positive submission."
        )
    else:
        caveats.append(
            "Whether the credit was utilised has not been established. If it "
            "was availed but not utilised, Section 50(3) does not apply at all "
            "— establish this from the electronic credit ledger before "
            "conceding any interest on the credit limbs."
        )
    result["caveats"] = caveats
    return result


# ---------------------------------------------------------------------------
# Penalty — Sections 73, 74, 122
# ---------------------------------------------------------------------------
# The concession windows are the point of this table. Under s.73 a taxpayer who
# pays before the notice pays NO penalty at all; within 30 days of the SCN,
# still nothing. Under s.74 the equivalent windows are 15% and 25%. Firms miss
# these because they are date-driven and the dates are not in the notice — they
# are computed from it.

    # Section 74A, inserted by the Finance (No. 2) Act 2024, governs FY 2024-25
    # onwards and replaces the s.73/s.74 split with one scheme carrying two
    # tracks. Two things differ and both cost money if missed: the concession
    # windows are SIXTY days, not thirty, and the post-order concession on the
    # fraud track (50% within 60 days of the order) has no s.73 equivalent.
    # These notices are arriving now, and a s.74A matter routed through the
    # s.74 table is advised on the wrong deadline.
PENALTY_STAGES = {
    "74A_non_fraud": [
        ("before_notice", 0.0,
         "Section 74A(8)(i): tax and interest paid before issue of the notice "
         "— no penalty is leviable in a case not involving fraud, wilful "
         "misstatement or suppression."),
        ("within_60_days", 0.0,
         "Section 74A(8)(i): tax and interest paid within SIXTY days of issue "
         "of the notice — no penalty is payable and proceedings are deemed "
         "concluded. Note the window is sixty days under Section 74A, not the "
         "thirty days that applied under Section 73."),
        ("on_order", 10.0,
         "Section 74A(5)(i): penalty of 10% of tax, or Rs. 10,000, whichever "
         "is higher, on determination by order."),
    ],
    "74A_fraud": [
        ("before_notice", 15.0,
         "Section 74A(9)(i): tax, interest and penalty at 15% paid before "
         "issue of the notice — proceedings are deemed concluded."),
        ("within_60_days", 25.0,
         "Section 74A(9)(ii): tax, interest and penalty at 25% paid within "
         "SIXTY days of the notice — proceedings are deemed concluded."),
        ("within_60_days_of_order", 50.0,
         "Section 74A(9)(iii): penalty reduced to 50% of the tax where the "
         "tax, interest and penalty are paid within sixty days of "
         "communication of the order. There is no equivalent concession on the "
         "non-fraud track — check this before advising that an order is final."),
        ("on_order", 100.0,
         "Section 74A(5)(ii): penalty equal to the tax determined by order, "
         "where fraud, wilful misstatement or suppression is established."),
    ],
    "73": [
        ("before_notice", 0.0,
         "Section 73(5)/(6): tax and interest paid before issue of the notice — "
         "no penalty is leviable and no notice shall be issued in respect of "
         "the amount so paid."),
        ("within_30_days", 0.0,
         "Section 73(8): tax and interest paid within 30 days of issue of the "
         "show cause notice — no penalty is payable and proceedings are deemed "
         "concluded."),
        ("on_order", 10.0,
         "Section 73(9): penalty of 10% of tax, or Rs. 10,000, whichever is "
         "higher, on determination by order."),
    ],
    "74": [
        ("before_notice", 15.0,
         "Section 74(5): tax, interest and penalty at 15% paid before issue of "
         "the notice — proceedings are deemed concluded."),
        ("within_30_days", 25.0,
         "Section 74(8): tax, interest and penalty at 25% paid within 30 days "
         "of the show cause notice — proceedings are deemed concluded."),
        ("on_order", 100.0,
         "Section 74(9)/(10): penalty equal to the tax determined by order. "
         "Reduced to 50% if paid within 30 days of the order (Section 74(11))."),
    ],
}

PENALTY_MINIMUM_73 = 10000.0
PENALTY_MINIMUM_74A = 10000.0

# Concession window per scheme, in days. s.74A doubled it to sixty.
CONCESSION_DAYS = {"73": 30, "74": 30, "74A_non_fraud": 60, "74A_fraud": 60}


def _penalty_scheme(section: str, fraud: Optional[bool] = None) -> Optional[str]:
    """
    Which penalty table governs.

    74A is tested BEFORE 74, because `startswith("74")` matches "74A" and
    silently routed a Section 74A notice — FY 2024-25 onwards, which is what is
    being issued now — through the Section 74 table: right rates on the fraud
    track by coincidence, wrong deadline by thirty days.
    """
    section = str(section or "").strip().upper().replace(" ", "")
    if section.startswith("74A"):
        # The section carries both tracks. Absent an established finding of
        # fraud the non-fraud track is the correct default: the ingredients
        # must be alleged AND established, and assuming them against the
        # taxpayer is not this module's call to make.
        return "74A_fraud" if fraud is True else "74A_non_fraud"
    if section.startswith("74"):
        return "74"
    if section.startswith("73"):
        return "73"
    return None


def penalty_options(section: str, tax: float,
                    notice_date: Any = None,
                    fraud: Optional[bool] = None) -> Dict[str, Any]:
    """
    What penalty is payable at each stage, and by when.

    The deadline attached to each stage is the whole value of this function.
    "25% if paid within 30 days" is not actionable; "25% (Rs. 79,362) if paid
    by 14.08.2026, 9 days from today" is.

    `fraud` selects the Section 74A track and is tri-state: None means nobody
    has established which, and the non-fraud track is used rather than
    assuming the ingredients of fraud against the taxpayer.
    """
    section = str(section or "").strip()
    key = _penalty_scheme(section, fraud)
    if key is None:
        return {
            "computed": False,
            "reason": f"Penalty stages are defined for Sections 73, 74 and "
                      f"74A. Section {section or '(not stated)'} is determined "
                      "on its own terms — see Section 122 for the offence-wise "
                      "table.",
        }
    if not tax or tax <= 0:
        return {"computed": False,
                "reason": "No tax amount to compute penalty on."}

    window = CONCESSION_DAYS[key]
    issued = _as_date(notice_date)
    deadline = issued + timedelta(days=window) if issued else None
    concession_stage = f"within_{window}_days"

    stages = []
    for stage, rate, note in PENALTY_STAGES[key]:
        penalty = tax * (rate / 100.0)
        if stage == "on_order" and key in ("73", "74A_non_fraud"):
            # s.73(9) and s.74A(5)(i) are both the HIGHER of 10% and
            # Rs. 10,000 — on a small limb the floor governs and a computed
            # 10% understates it.
            penalty = max(penalty, PENALTY_MINIMUM_73 if key == "73"
                          else PENALTY_MINIMUM_74A)
        stages.append({
            "stage": stage,
            "rate": rate,
            "amount": round(penalty, 2),
            "note": note,
            "deadline": deadline.isoformat()
            if deadline and stage == concession_stage else None,
        })

    caveats = [
        f"Penalty stages are driven by the date of payment. Confirm the date "
        f"of service of the notice — not its date of issue — before relying on "
        f"the {window}-day window."
    ]
    if not issued:
        caveats.append(
            f"The date of the notice is not on file, so the {window}-day "
            "concession deadline could not be computed. Enter it before "
            "advising on this."
        )
    if key.startswith("74A"):
        caveats.append(
            "Section 74A governs FY 2024-25 onwards; Sections 73 and 74 "
            "continue to govern periods up to FY 2023-24. Confirm the period "
            "in issue selects the right scheme."
        )
        caveats.append(
            "The concession window under Section 74A is SIXTY days, not the "
            "thirty days that applied under Sections 73 and 74."
        )
    if key == "74A_non_fraud" and fraud is None:
        caveats.append(
            "Computed on the NON-FRAUD track, because no finding of fraud, "
            "wilful misstatement or suppression has been established on the "
            "file. If the department has alleged and made out those "
            "ingredients the fraud track applies and the figures are higher — "
            "and if it has merely alleged them, contest the characterisation, "
            "because it is what selects this table."
        )

    return {
        "computed": True,
        "section": key,
        "scheme": "74A" if key.startswith("74A") else key,
        "track": ("fraud" if key == "74A_fraud"
                  else "non_fraud" if key == "74A_non_fraud" else None),
        "tax": round(float(tax), 2),
        "stages": stages,
        "concession_days": window,
        "concession_deadline": deadline.isoformat() if deadline else None,
        "caveats": caveats,
    }


# ---------------------------------------------------------------------------
# Appeal — pre-deposit under Sections 107 and 112
# ---------------------------------------------------------------------------
# These numbers decide whether an appeal is filed at all, and they are asked of
# a firm within a day of the order arriving. The caps were reduced by the
# Finance (No. 2) Act 2024; the values below are the reduced ones. As with
# everything else here, the grounding stage confirms the live position and this
# module does the arithmetic under it.

PREDEPOSIT_107_RATE = 10.0
PREDEPOSIT_107_CAP = 20_00_00_000.0       # Rs. 20 crore per head (CGST + SGST)
PREDEPOSIT_112_RATE = 10.0
PREDEPOSIT_112_CAP = 20_00_00_000.0
PREDEPOSIT_PENALTY_ONLY_129 = 25.0        # s.107(6) proviso — detention penalty


def predeposit(disputed_tax: float, forum: str = "107",
               penalty_only: bool = False) -> Dict[str, Any]:
    """
    Pre-deposit payable to maintain an appeal.

    Computed on the tax IN DISPUTE, not on the total demand — a distinction
    that matters whenever part of the order is accepted, which is the usual
    case once a limb-wise reply has already conceded three limbs and paid them.
    """
    if disputed_tax is None or disputed_tax <= 0:
        return {"computed": False,
                "reason": "The disputed tax must be stated before the "
                          "pre-deposit can be computed."}

    forum = str(forum or "107")
    if penalty_only:
        amount = disputed_tax * (PREDEPOSIT_PENALTY_ONLY_129 / 100.0)
        return {
            "computed": True,
            "forum": "107",
            "rate": PREDEPOSIT_PENALTY_ONLY_129,
            "amount": round(amount, 2),
            "working": f"25% of Rs. {disputed_tax:,.2f} = Rs. {amount:,.2f}",
            "basis": "Proviso to Section 107(6): where the dispute is of "
                     "penalty alone under Section 129(3), the pre-deposit is "
                     "25% of the penalty.",
        }

    if forum.startswith("112"):
        rate, cap, basis = (
            PREDEPOSIT_112_RATE, PREDEPOSIT_112_CAP,
            "Section 112(8): a further 10% of the tax in dispute, over and "
            "above the amount deposited under Section 107, to maintain an "
            "appeal to the Appellate Tribunal.",
        )
    else:
        rate, cap, basis = (
            PREDEPOSIT_107_RATE, PREDEPOSIT_107_CAP,
            "Section 107(6): 10% of the tax in dispute, subject to the "
            "statutory cap, to maintain a first appeal.",
        )

    uncapped = disputed_tax * (rate / 100.0)
    amount = min(uncapped, cap)

    return {
        "computed": True,
        "forum": "112" if forum.startswith("112") else "107",
        "rate": rate,
        "amount": round(amount, 2),
        "capped": uncapped > cap,
        "working": (f"{rate}% of Rs. {disputed_tax:,.2f} = Rs. {uncapped:,.2f}"
                    + (f", restricted to the cap of Rs. {cap:,.2f}"
                       if uncapped > cap else "")),
        "basis": basis,
        "caveats": [
            "Computed on the tax in dispute. Where part of the order is "
            "accepted and paid, the pre-deposit is on the balance only.",
            "The cap applies per Act — the same amount again is payable under "
            "the SGST Act on a combined demand.",
        ],
    }


# ---------------------------------------------------------------------------
# Limitation — Sections 73(10), 74(10), 107(1), 112(1)
# ---------------------------------------------------------------------------

# Section 107 speaks in MONTHS, and a month is a calendar month under section
# 3(35) of the General Clauses Act 1897, not thirty days. Computing 90 + 30
# days instead moved the deadline by up to two days at the margins, in both
# directions — enough to report an in-time appeal as condonable, or a
# condonable one as time-barred, which is the class of advice a firm is sued
# over. The day counts are still reported, because that is what a reviewer
# checks against a diary; they are no longer what the dates are computed from.
APPEAL_WINDOW_MONTHS_107 = 3
APPEAL_CONDONABLE_MONTHS_107 = 1


def _add_months(start: date, months: int) -> date:
    """
    The same day of the month, `months` later, clamped to the month's end.

    Clamping is the rule the courts apply to a period expressed in months
    where the target month is shorter: an order communicated on 31 March gives
    30 June, not 1 July. Getting this wrong lengthens limitation by a day at
    exactly the boundary where it is argued.
    """
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        last_day = 31
    else:
        last_day = (date(year + (month == 12), month % 12 + 1, 1)
                    - timedelta(days=1)).day
    return date(year, month, min(start.day, last_day))


def appeal_limitation(order_date: Any, as_on: Any = None) -> Dict[str, Any]:
    """
    Whether an appeal under Section 107 is still in time, and for how long.

    Returns the condonable window separately from the ordinary one. An appeal
    filed on day 100 is not out of time — it is late and needs an application
    for condonation, which is a different piece of drafting and a different
    conversation with the client.
    """
    served = _as_date(order_date)
    if served is None:
        return {"computed": False,
                "reason": "The date of communication of the order is needed "
                          "to compute limitation."}

    today = _as_date(as_on) or date.today()
    ordinary = _add_months(served, APPEAL_WINDOW_MONTHS_107)
    condonable = _add_months(ordinary, APPEAL_CONDONABLE_MONTHS_107)
    days_left = (ordinary - today).days

    if today <= ordinary:
        status, message = "in_time", (
            f"In time. {days_left} day(s) remain of the three-month period, "
            f"which expires on {ordinary.strftime('%d.%m.%Y')}."
        )
    elif today <= condonable:
        status, message = "condonable", (
            f"The three-month period expired on {ordinary.strftime('%d.%m.%Y')}. "
            f"The appeal may still be admitted on sufficient cause shown until "
            f"{condonable.strftime('%d.%m.%Y')} — file with an application for "
            "condonation of delay supported by an affidavit."
        )
    else:
        status, message = "time_barred", (
            f"The condonable period expired on "
            f"{condonable.strftime('%d.%m.%Y')}. The Appellate Authority has no "
            "power to condone beyond one further month (Section 107(4)); the "
            "remedy, if any, lies in a writ petition. Advise the client "
            "expressly and record the advice."
        )

    return {
        "computed": True,
        "status": status,
        "message": message,
        "order_date": served.isoformat(),
        "as_on": today.isoformat(),
        "ordinary_deadline": ordinary.isoformat(),
        "condonable_deadline": condonable.isoformat(),
        "days_remaining": days_left,
        "basis": "Section 107(1) — three months from the date on which the "
                 "order is communicated; Section 107(4) — one further month on "
                 "sufficient cause. Computed in calendar months per section "
                 "3(35) of the General Clauses Act, 1897, not as 90 and 30 "
                 "days.",
        "caveats": [
            "Time runs from COMMUNICATION of the order, not from its date. "
            "Where the order was uploaded to the portal without separate "
            "service, the date of knowledge is arguable and is often the point "
            "on which a late appeal is admitted."
        ],
    }


# ---------------------------------------------------------------------------
# Amnesty — Section 128A
# ---------------------------------------------------------------------------
# s.128A waives interest and penalty on demands under s.73 for FY 2017-18,
# 2018-19 and 2019-20, where the tax is paid in full. It does NOT touch s.74
# demands, and it does not touch the tax itself. Eligibility is mechanical —
# section, year, and whether tax has been paid — which is exactly why it should
# never be left to a model to decide.

AMNESTY_YEARS = ("2017-18", "2018-19", "2019-20")


def amnesty_128a(section: str, tax_period: str,
                 tax_paid: Optional[bool] = None) -> Dict[str, Any]:
    """
    Whether Section 128A is available on this limb.

    Returns eligibility plus the reason, so an ineligible matter carries the
    explanation rather than a bare no — the client asks why, every time.
    """
    section = str(section or "").strip()
    period = _normalise_period(tax_period)

    reasons: List[str] = []
    eligible = True

    if section.replace(" ", "").upper().startswith("74A"):
        # Reached the same wrong branch as the penalty table did: "74A"
        # startswith "74". The outcome (ineligible) was right, the reason given
        # to the client was not, and a wrong reason on an eligibility question
        # is what gets argued back.
        eligible = False
        reasons.append(
            "Section 128A covers demands under Section 73 for FY 2017-18 to "
            "2019-20. This demand is under Section 74A, which governs FY "
            "2024-25 onwards — the waiver cannot reach it on either the "
            "section or the year, and no re-characterisation argument is "
            "available here."
        )
    elif section.startswith("74"):
        eligible = False
        reasons.append(
            "Section 128A applies only to demands under Section 73. This "
            "demand is under Section 74 (fraud, wilful misstatement or "
            "suppression), which is outside the waiver. Where the s.74 "
            "invocation is itself contested and the ingredients are not made "
            "out, a successful re-characterisation to s.73 would bring the "
            "matter within 128A — that is a reason to contest the "
            "characterisation, not merely the quantum."
        )
    elif not section.startswith("73"):
        eligible = False
        reasons.append(
            f"Section 128A covers demands under Section 73. The provision "
            f"invoked here is Section {section or '(not stated)'} — confirm the "
            "section before ruling the waiver in or out."
        )

    if period is None:
        eligible = False
        reasons.append(
            "The tax period could not be read, so eligibility by year could "
            "not be determined. Section 128A covers FY 2017-18, 2018-19 and "
            "2019-20 only."
        )
    elif period not in AMNESTY_YEARS:
        eligible = False
        reasons.append(
            f"Section 128A covers FY 2017-18, 2018-19 and 2019-20. This matter "
            f"is for FY {period}, which is outside the waiver."
        )

    if eligible and tax_paid is False:
        reasons.append(
            "Eligible by section and year, but the waiver operates only where "
            "the full amount of tax demanded is paid. The tax is recorded as "
            "unpaid — the waiver is available but not yet earned."
        )
    elif eligible and tax_paid is None:
        reasons.append(
            "Eligible by section and year. The waiver is conditional on payment "
            "of the full tax demanded — confirm the payment position."
        )
    elif eligible:
        reasons.append(
            "Eligible by section and year, and the tax is recorded as paid. "
            "Interest and penalty are liable to be waived on application."
        )

    return {
        "eligible": eligible,
        "section": section,
        "tax_period": period,
        "reasons": reasons,
        "form": "SPL-01 (where no notice/order) or SPL-02 (against an order)",
        "caveats": [
            "Section 128A requires withdrawal of any appeal or writ against "
            "the same demand as a condition of the waiver. Weigh this against "
            "the strength of the contested limbs before applying.",
            "The application window and the payment deadline are notified and "
            "have been extended more than once. Confirm the dates currently in "
            "force before advising — this module does not track them.",
        ],
    }


def _normalise_period(value: Any) -> Optional[str]:
    """'FY 2019-20', '2019-20', '2019-2020' → '2019-20'."""
    import re
    text = str(value or "")
    match = re.search(r"(20\d{2})\s*[-–/]\s*(\d{2,4})", text)
    if not match:
        return None
    start, end = match.group(1), match.group(2)
    if len(end) == 4:
        end = end[2:]
    return f"{start}-{end}"


# ---------------------------------------------------------------------------
# Matter-level assembly
# ---------------------------------------------------------------------------


def matter_computations(matter: Dict[str, Any]) -> Dict[str, Any]:
    """
    Every computation this matter supports, with everything it does not.

    Deliberately tolerant of an incomplete file: a matter that has not yet had
    payment dates entered still gets its penalty stages and its amnesty
    position, and the interest working reports what it needs rather than
    failing. Half a working note is worth having; a blank one because a date
    was missing is not.
    """
    intake = matter.get("intake") or matter
    section = str(intake.get("section_invoked") or "")
    period = intake.get("tax_period")
    notice_date = intake.get("notice_date")
    limbs = intake.get("defects") or []

    tax_total = 0.0
    for limb in limbs:
        heads = limb.get("amount_by_head") or {}
        tax_total += sum(v for v in heads.values() if isinstance(v, (int, float)))
    if not tax_total:
        tax_total = float(intake.get("amount_disputed") or 0)

    computations: Dict[str, Any] = {
        "penalty": penalty_options(section, tax_total, notice_date,
                                   fraud=intake.get("fraud_established")),
        "amnesty_128a": amnesty_128a(section, period,
                                     intake.get("tax_paid")),
    }

    # An order on file means the appeal clock is running, and that is the most
    # time-critical number in the matter.
    order_date = intake.get("order_date") or (
        intake.get("notice_date") if str(intake.get("notice_type") or "")
        .upper().startswith("DRC-07") else None
    )
    if order_date:
        computations["appeal_limitation"] = appeal_limitation(order_date)
        computations["predeposit_107"] = predeposit(tax_total, "107")

    return {
        "tax_base": round(tax_total, 2),
        "section": section,
        "computations": computations,
        "note": (
            "Computed locally under the provisions named, not by a model. "
            "Every figure carries its own working and is to be checked against "
            "the electronic liability register before it is offered to the "
            "department."
        ),
    }
