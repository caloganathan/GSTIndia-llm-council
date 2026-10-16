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

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Interest — Section 50
# ---------------------------------------------------------------------------
# s.50(1): 18% per annum on tax not paid or short paid, from the day after the
#          due date of the return to the date of payment.
# s.50(3): substituted by section 111 of the Finance Act 2022, retrospectively
#          w.e.f. 1 July 2017, so that it applies ONLY to input tax credit that
#          was wrongly availed AND utilised. Availment alone, reversed without
#          utilisation, does not attract s.50(3) — the distinction is worth
#          real money and is routinely conceded by taxpayers who never checked
#          whether the credit was utilised at all.
#
# THE s.50(3) RATE IS 18%, NOT 24%. The substituted section carries a CEILING
# of "not exceeding twenty-four per cent"; the rate actually notified is
# eighteen. Notification No. 13/2017-Central Tax originally notified 24% for
# s.50(3); section 116 of the Finance Act 2022, read with its Sixth Schedule,
# amended that notification retrospectively to 18% w.e.f. 1 July 2017. (The
# s.50(3) substitution itself was brought into force by Notification No.
# 09/2022-Central Tax dated 05.07.2022, and Rule 88B was inserted the same day
# by Notification No. 14/2022-Central Tax.) This constant read 24.0 until
# September 2026, which overstated interest on every utilised-credit limb by a third — in a module
# whose whole claim is that its arithmetic can be trusted because it is code.
# The ceiling is not the rate; do not "restore" 24 from the section text.
INTEREST_RATE_NORMAL = 18.0
INTEREST_RATE_ITC_UTILISED = 18.0

# The proviso to s.50(1): where the return for a period is filed after the due
# date, interest on the tax DECLARED IN THAT RETURN runs only on the portion
# discharged in cash, not on the portion set off against credit. This is a
# live and frequently missed relief — but it has two limits that matter on
# exactly the matters this product handles, and both are stated here:
#   1. It does not apply where the return is furnished after the commencement
#      of proceedings under s.73, s.74 or s.74A for that period.
#   2. It reaches tax declared in the return for the period itself, not a
#      liability discovered later and paid by DRC-03 or in a subsequent return.
CASH_LEDGER_PROVISO = (
    "Proviso to Section 50(1): where the return for the period is furnished "
    "after the due date, interest on the tax declared in that return is "
    "payable only on the portion discharged by debit to the electronic cash "
    "ledger. The relief does NOT apply where the return was furnished after "
    "the commencement of proceedings under Section 73, 74 or 74A for the "
    "period, nor to a liability first discharged through DRC-03 or a later "
    "return. Confirm both points and the cash/credit split before adopting "
    "the figure below, which is computed on the whole amount."
)

# Rule 88B(3): interest under s.50(3) runs from the date of UTILISATION of the
# wrongly availed credit to the date of its reversal or payment — not from the
# due date of the return — and credit is treated as utilised only when, and to
# the extent that, the balance in the electronic credit ledger falls below the
# amount wrongly availed.
RULE_88B_PERIOD = (
    "Rule 88B(3): interest on wrongly availed and utilised credit runs from "
    "the date of UTILISATION to the date of reversal or payment, and credit is "
    "utilised only when and to the extent the electronic credit ledger balance "
    "falls below the amount wrongly availed. Confirm the start date entered "
    "is the date of utilisation, not the due date of the return."
)

DAYS_IN_YEAR = 365


def _inr(value: float) -> str:
    """Indian digit grouping (3,17,450.00), as the workings are read in India."""
    from .defects import indian_number
    text = indian_number(round(float(value), 2))
    whole, _, paise = text.partition(".")
    return f"{whole}.{(paise + '00')[:2]}"


def _num(value: Any) -> Optional[float]:
    """A number from a number or a formatted string ('1,23,456', 'Rs. 500')."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"(?i)rs\.?|inr|₹|,|\s", "", str(value))
    try:
        return float(text)
    except ValueError:
        return None


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
            f"Rs. {_inr(amount)} x {rate}% x {days}/{DAYS_IN_YEAR} days "
            f"({start.strftime('%d.%m.%Y')} to {end.strftime('%d.%m.%Y')}) "
            f"= Rs. {_inr(interest)}"
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

    `itc_utilised` is tri-state on purpose, and it applies to CREDIT limbs.

    True  — s.50(3), at the 18% notified under it (not the 24% ceiling in the
            section's text), with the Rule 88B period caveat.
    False — credit availed but NOT utilised. No interest arises: s.50(3) is
            confined to credit availed AND utilised, and no tax was short paid
            to engage s.50(1). The result is a computed NIL with its reason —
            a defence, flagged as one. (Before September 2026 this branch
            computed 18% under s.50(1) while its own caveat said no interest
            arose, and once the s.50(3) rate was corrected to 18% the two
            branches produced the same figure.)
    None  — nobody has established which, or the limb is not a credit limb.
            s.50(1) at 18% is computed, and the working says utilisation is
            open rather than defaulting to the position safer for the
            department.
    """
    if itc_utilised is True:
        result = compute_interest(amount, due_date, payment_date,
                                  INTEREST_RATE_ITC_UTILISED, "Section 50(3)")
        result["caveats"] = [
            "Section 50(3) applies only where the credit was both wrongly "
            "availed AND utilised. Confirm utilisation from the electronic "
            "credit ledger before this figure is offered.",
            "Rate: 18% per annum — Notification No. 13/2017-Central Tax as "
            "amended retrospectively w.e.f. 01.07.2017 by section 116 of, and "
            "the Sixth Schedule to, the Finance Act 2022. The 24% in the text "
            "of Section 50(3) is a ceiling, not the notified rate; resist any "
            "demand computed at 24%.",
            RULE_88B_PERIOD,
        ]
        return result

    if itc_utilised is False:
        if amount is None or amount <= 0:
            return compute_interest(amount, due_date, payment_date,
                                    INTEREST_RATE_ITC_UTILISED,
                                    "Section 50(3)")
        return {
            "computed": True,
            "amount": 0.0,
            "principal": round(float(amount), 2),
            "rate": None,
            "days": None,
            "from_date": None,
            "to_date": None,
            "basis": "Section 50(3) — not attracted",
            "working": (
                f"Nil. Credit of Rs. {_inr(amount)} was availed but not "
                "utilised; Section 50(3) charges interest only on credit "
                "wrongly availed AND utilised, and no tax was short paid to "
                "engage Section 50(1)."
            ),
            "caveats": [
                "Credit availed but NOT utilised: following the retrospective "
                "substitution of Section 50(3) (section 111, Finance Act 2022, "
                "w.e.f. 01.07.2017), interest does not arise at all on these "
                "facts. This is a ground of defence — take it as a positive "
                "submission, supported by the electronic credit ledger "
                "showing the balance never fell below the amount in dispute "
                "(Rule 88B(3)).",
                "If the ledger balance DID fall below the disputed amount at "
                "any point, the credit was utilised to that extent from that "
                "date, and interest at 18% runs on that portion only.",
            ],
        }

    result = compute_interest(amount, due_date, payment_date,
                              INTEREST_RATE_NORMAL, "Section 50(1)")
    result["caveats"] = [
        CASH_LEDGER_PROVISO,
        "If this is a credit limb, whether the credit was utilised has not "
        "been established. If it was availed but not utilised, no interest "
        "arises at all (Section 50(3)); if utilised, interest runs only from "
        "the date of utilisation (Rule 88B(3)) — establish this from the "
        "electronic credit ledger before conceding any interest on the credit "
        "limbs.",
    ]
    return result


# ---------------------------------------------------------------------------
# Penalty — Sections 73, 74, 122
# ---------------------------------------------------------------------------
# The concession windows are the point of this table. Under s.73 a taxpayer who
# pays before the notice pays NO penalty at all; within 30 days of the SCN,
# still nothing. Under s.74 the equivalent windows are 15% and 25%. Firms miss
# these because they are date-driven and the dates are not in the notice — they
# are computed from it.
#
# Section 74A, inserted by the Finance (No. 2) Act 2024, governs FY 2024-25
# onwards and replaces the s.73/s.74 split with one scheme carrying two
# tracks. Two things differ and both cost money if missed: the concession
# windows are SIXTY days, not thirty, and the post-order concession on the
# fraud track is 50% within SIXTY days of the order (s.74(11) gives thirty).
# Neither non-fraud track (s.73, s.74A) has a post-order concession. These
# notices are arriving now, and a s.74A matter routed through the s.74 table
# is advised on the wrong deadline.
PENALTY_STAGES = {
    "74A_non_fraud": [
        ("before_notice", 0.0,
         "Section 74A(8)(i): tax and interest paid before issue of the notice "
         "— no penalty is leviable in a case not involving fraud, wilful "
         "misstatement or suppression."),
        ("within_60_days", 0.0,
         "Section 74A(8)(ii): tax and interest paid within SIXTY days of issue "
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
        ("within_30_days_of_order", 50.0,
         "Section 74(11): penalty reduced to 50% of the tax where the tax, "
         "interest and penalty are paid within 30 days of communication of "
         "the order — proceedings are deemed concluded."),
        ("on_order", 100.0,
         "Section 74(9): penalty equal to the tax determined by order."),
    ],
}

PENALTY_MINIMUM_73 = 10000.0
PENALTY_MINIMUM_74A = 10000.0

# Concession window per scheme, in days. s.74A doubled it to sixty.
CONCESSION_DAYS = {"73": 30, "74": 30, "74A_non_fraud": 60, "74A_fraud": 60}


_SECTION_PREFIX_RE = re.compile(
    r"^\s*(?:u\s*/\s*s\.?|under\s+section|section|sec\.?|s\.)\s*", re.I)


def _clean_section(section: Any) -> str:
    """'Section 73', 'u/s 74', 'Sec. 74A(1)' → '73', '74', '74A(1)'."""
    return _SECTION_PREFIX_RE.sub("", str(section or "")).strip()


def _penalty_scheme(section: str, fraud: Optional[bool] = None) -> Optional[str]:
    """
    Which penalty table governs.

    74A is tested BEFORE 74, because `startswith("74")` matches "74A" and
    silently routed a Section 74A notice — FY 2024-25 onwards, which is what is
    being issued now — through the Section 74 table: right rates on the fraud
    track by coincidence, wrong deadline by thirty days.
    """
    section = _clean_section(section).upper().replace(" ", "")
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


ORDER_CONCESSION_DAYS = {"74": 30, "74A_fraud": 60}


def penalty_options(section: str, tax: float,
                    notice_date: Any = None,
                    fraud: Optional[bool] = None,
                    order_date: Any = None) -> Dict[str, Any]:
    """
    What penalty is payable at each stage, and by when.

    The deadline attached to each stage is the whole value of this function.
    "25% if paid within 30 days" is not actionable; "25% (Rs. 79,362) if paid
    by 14.08.2026, 9 days from today" is.

    `fraud` selects the Section 74A track and is tri-state: None means nobody
    has established which, and the non-fraud track is used rather than
    assuming the ingredients of fraud against the taxpayer.

    `notice_date` is the date of issue of the SHOW CAUSE NOTICE. `order_date`
    is the date of communication of the order, and dates the post-order
    concession where one exists (s.74(11): 30 days; s.74A(9)(iii): 60 days).
    """
    section = _clean_section(section)
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
    ordered = _as_date(order_date)
    order_window = ORDER_CONCESSION_DAYS.get(key)
    order_deadline = (ordered + timedelta(days=order_window)
                      if ordered and order_window else None)
    order_stage = f"within_{order_window}_days_of_order" if order_window else None

    stages = []
    for stage, rate, note in PENALTY_STAGES[key]:
        penalty = tax * (rate / 100.0)
        if stage == "on_order" and key in ("73", "74A_non_fraud"):
            # s.73(9) and s.74A(5)(i) are both the HIGHER of 10% and
            # Rs. 10,000 — on a small limb the floor governs and a computed
            # 10% understates it.
            penalty = max(penalty, PENALTY_MINIMUM_73 if key == "73"
                          else PENALTY_MINIMUM_74A)
        if stage == concession_stage and deadline:
            stage_deadline = deadline.isoformat()
        elif stage == order_stage and order_deadline:
            stage_deadline = order_deadline.isoformat()
        else:
            stage_deadline = None
        stages.append({
            "stage": stage,
            "rate": rate,
            "amount": round(penalty, 2),
            "note": note,
            "deadline": stage_deadline,
        })

    caveats = [
        f"Penalty stages are driven by the date of payment. The {window}-day "
        f"window runs from ISSUE of the show cause notice (Sections 73(8), "
        f"74(8), 74A(8)(ii) and 74A(9)(ii)), not from its service — compute "
        f"from the date of issue, and do not advise a later deadline on the "
        f"strength of a later date of service."
    ]
    if not issued:
        caveats.append(
            f"The date of the show cause notice is not on file, so the "
            f"{window}-day concession deadline could not be computed. Enter "
            "it before advising on this."
        )
    if ordered:
        caveats.append(
            "An order is on file, so the pre-order stages have passed; they "
            "are shown for the record of what the matter would have cost."
            + (f" The post-order concession runs to "
               f"{order_deadline.strftime('%d.%m.%Y')}." if order_deadline
               else " There is no post-order concession on this scheme.")
        )
    if key in ("73", "74A_non_fraud"):
        sub = "73(11)" if key == "73" else "74A(11)"
        caveats.append(
            f"Section {sub}: the nil-penalty stages do NOT apply to "
            "self-assessed tax, or tax collected, that was not paid within "
            "thirty days of its due date — for that portion the order-stage "
            "penalty (10% or Rs. 10,000, whichever is higher) is payable even "
            "if the tax is paid before or soon after the notice. A limb "
            "raising tax declared in GSTR-1 but not paid through GSTR-3B is "
            "the usual case. Split the tax on that basis before advising."
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
        "order_concession_deadline": (order_deadline.isoformat()
                                      if order_deadline else None),
        "caveats": caveats,
    }


# ---------------------------------------------------------------------------
# Appeal — pre-deposit under Sections 107 and 112
# ---------------------------------------------------------------------------
# These numbers decide whether an appeal is filed at all, and they are asked of
# a firm within a day of the order arriving. As with everything else here, the
# grounding stage confirms the live position and this module does the
# arithmetic under it.
#
# The caps were reduced by the Finance (No. 2) Act 2024 (in force 01.11.2024):
#   s.107(6)(b)  10% of tax in dispute, cap Rs. 20 crore (was 25) — per Act
#   s.112(8)(b)  a further 10% (was 20%), cap Rs. 20 crore (was 50) — per Act
#   s.20 IGST    the same, with each cap read as Rs. 40 crore for IGST
#
# The cap is PER ACT. A combined CGST + SGST demand is two appeals' worth of
# deposit, each capped separately on its own head. Earlier revisions applied
# one cap to the combined total and then told the reader "the same amount
# again is payable under the SGST Act" — which double-counted the SGST that
# was already in the total. `predeposit_by_head` is the correct entry point
# whenever the head split is known.
#
# Penalty-only orders: the Finance Act 2025 substituted the proviso to s.107(6)
# and inserted one to s.112(8), w.e.f. 01.10.2025. An appeal against an order
# demanding penalty WITHOUT any demand of tax now needs 10% of the penalty at
# each forum — and that now includes s.129(3) detention orders, whose deposit
# was 25% until then.

PREDEPOSIT_107_RATE = 10.0
PREDEPOSIT_107_CAP = 20_00_00_000.0       # Rs. 20 crore, per Act (CGST; SGST/UTGST)
PREDEPOSIT_112_RATE = 10.0
PREDEPOSIT_112_CAP = 20_00_00_000.0       # Rs. 20 crore, per Act
PREDEPOSIT_IGST_CAP = 40_00_00_000.0      # s.20 IGST Act — Rs. 40 crore
PREDEPOSIT_PENALTY_ONLY = 10.0            # provisos to s.107(6) / s.112(8), FA 2025
PENALTY_ONLY_PROVISO_FROM = date(2025, 10, 1)

_HEAD_LABELS = {"cgst": "CGST", "sgst": "SGST/UTGST", "igst": "IGST",
                "cess": "Compensation Cess"}


def _cap_for(forum: str, head: Optional[str]) -> float:
    if str(head or "").lower() == "igst":
        return PREDEPOSIT_IGST_CAP
    return PREDEPOSIT_112_CAP if forum == "112" else PREDEPOSIT_107_CAP


def predeposit(disputed_tax: float, forum: str = "107",
               penalty_only: bool = False,
               head: Optional[str] = None) -> Dict[str, Any]:
    """
    Pre-deposit payable to maintain an appeal, under ONE Act.

    Computed on the tax IN DISPUTE, not on the total demand — a distinction
    that matters whenever part of the order is accepted, which is the usual
    case once a limb-wise reply has already conceded three limbs and paid them.

    `head` selects the cap: "igst" is capped at Rs. 40 crore, every other head
    at Rs. 20 crore. With `penalty_only`, `disputed_tax` is the PENALTY in
    dispute on an order that demands no tax.
    """
    if disputed_tax is None or disputed_tax <= 0:
        return {"computed": False,
                "reason": "The disputed tax must be stated before the "
                          "pre-deposit can be computed."}

    forum = "112" if str(forum or "107").startswith("112") else "107"

    if penalty_only:
        rate = PREDEPOSIT_PENALTY_ONLY
        amount = disputed_tax * (rate / 100.0)
        basis = (
            "Proviso to Section 107(6), as substituted by the Finance Act "
            "2025 w.e.f. 01.10.2025: where the order demands penalty without "
            "any demand of tax (including an order under Section 129(3)), 10% "
            "of the penalty must be deposited to maintain a first appeal."
            if forum == "107" else
            "Proviso to Section 112(8), inserted by the Finance Act 2025 "
            "w.e.f. 01.10.2025: a further 10% of the penalty, over and above "
            "the amount deposited under Section 107(6), where the order "
            "demands penalty without any demand of tax."
        )
        return {
            "computed": True,
            "forum": forum,
            "rate": rate,
            "amount": round(amount, 2),
            "capped": False,
            "working": f"{rate:g}% of penalty of Rs. {_inr(disputed_tax)} "
                       f"= Rs. {_inr(amount)}",
            "basis": basis,
            "caveats": [
                "Before 01.10.2025 a penalty-only order other than one under "
                "Section 129(3) needed no pre-deposit, and a Section 129(3) "
                "order needed 25%. Where the SHOW CAUSE NOTICE was issued "
                "before 01.10.2025, the new deposit has been held "
                "inapplicable even to an order passed after that date — "
                "Gaurav Jain v. Joint Commissioner (Appeals-II), CGST Delhi "
                "Zone (Delhi High Court, Division Bench, 31.07.2026), and "
                "GSTAT Hyderabad to the same effect. Binding in Delhi, "
                "persuasive elsewhere; check the SCN date before computing "
                "a deposit that may not be owed.",
            ],
        }

    rate = PREDEPOSIT_112_RATE if forum == "112" else PREDEPOSIT_107_RATE
    cap = _cap_for(forum, head)
    basis = (
        "Section 112(8)(b): a further 10% of the tax in dispute, over and "
        "above the amount deposited under Section 107(6), to maintain an "
        "appeal to the Appellate Tribunal, subject to the cap."
        if forum == "112" else
        "Section 107(6): the admitted amount in full, plus 10% of the "
        "remaining tax in dispute, subject to the cap, to maintain a first "
        "appeal."
    )

    uncapped = disputed_tax * (rate / 100.0)
    amount = min(uncapped, cap)

    return {
        "computed": True,
        "forum": forum,
        "head": head,
        "rate": rate,
        "amount": round(amount, 2),
        "capped": uncapped > cap,
        "working": (f"{rate:g}% of Rs. {_inr(disputed_tax)} = Rs. {_inr(uncapped)}"
                    + (f", restricted to the cap of Rs. {_inr(cap)}"
                       if uncapped > cap else "")),
        "basis": basis,
        "caveats": [
            "Computed on the tax in dispute. Where part of the order is "
            "accepted, the admitted amount is paid in full and the "
            "pre-deposit is on the balance only.",
            "The cap applies separately under each Act — Rs. 20 crore each "
            "under the CGST and SGST/UTGST Acts, Rs. 40 crore under the IGST "
            "Act. This figure is for one Act only; use the head-wise "
            "computation where the demand spans more than one.",
        ],
    }


def predeposit_by_head(heads: Dict[str, Any], forum: str = "107") -> Dict[str, Any]:
    """
    Pre-deposit across a head-wise demand, each head capped under its own Act.

    An `unallocated` amount cannot be assigned an Act, so it is computed
    separately at the lower cap and flagged — the reviewer sees it, rather
    than it being guessed into CGST.
    """
    rows = []
    total = 0.0
    capped = False
    for head in ("igst", "cgst", "sgst", "cess", "unallocated"):
        value = heads.get(head) if isinstance(heads, dict) else None
        if not isinstance(value, (int, float)) or value <= 0:
            continue
        row = predeposit(float(value), forum,
                         head=None if head == "unallocated" else head)
        row["head"] = head
        rows.append(row)
        total += row["amount"]
        capped = capped or row.get("capped", False)

    if not rows:
        return {"computed": False,
                "reason": "The disputed tax must be stated before the "
                          "pre-deposit can be computed."}

    forum = rows[0]["forum"]
    working = "; ".join(
        f"{_HEAD_LABELS.get(r['head'], 'Head not split')}: {r['working']}"
        for r in rows)
    caveats = [
        "Computed on the tax in dispute. Where part of the order is accepted, "
        "the admitted amount is paid in full and the pre-deposit is on the "
        "balance only.",
        "Each head is capped under its own Act — Rs. 20 crore under each of "
        "the CGST and SGST/UTGST Acts, Rs. 40 crore under the IGST Act "
        "(Section 20, IGST Act). The total is the sum of those "
        "separate deposits.",
    ]
    if any(r["head"] == "unallocated" for r in rows):
        caveats.append(
            "Part of the demand is not split by head, so it was computed "
            "against the Rs. 20 crore cap. Split it by head before relying "
            "on the figure for a large demand.")
    if any(r["head"] == "cess" for r in rows):
        caveats.append(
            "Compensation Cess follows the CGST Act's appeal provisions "
            "through section 11 of the GST (Compensation to States) Cess Act; "
            "it is computed here at the CGST cap.")

    return {
        "computed": True,
        "forum": forum,
        "rate": rows[0]["rate"],
        "amount": round(total, 2),
        "capped": capped,
        "by_head": rows,
        "working": working + f" — total Rs. {_inr(total)}",
        "basis": rows[0]["basis"],
        "caveats": caveats,
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

# Section 112 (Appellate Tribunal): three months, plus three condonable
# (s.112(6)). Section 112(1), as amended by the Finance (No. 2) Act 2024, runs
# the three months from communication OR a date notified for the Tribunal,
# whichever is later. The Tribunal became operational on 24.09.2025. S.O.
# 4220(E) of 17.09.2025 notified 30.06.2026 as the last date for orders
# communicated before 01.04.2026; S.O. 3502(E) of 30.06.2026 moved BOTH the
# date (to 31.07.2026) and the cohort (to orders communicated before
# 01.05.2026). Orders communicated on or after 01.05.2026 run the ordinary
# three months. These are notified dates, and a further notification would
# change them — the caveat says so every time. (The first cut of this table
# kept the old 01.04.2026 cohort, which reported every April 2026 order as
# out of time from mid-July.)
APPEAL_WINDOW_MONTHS_112 = 3
APPEAL_CONDONABLE_MONTHS_112 = 3
GSTAT_BACKLOG_CUTOFF = date(2026, 5, 1)
GSTAT_BACKLOG_LAST_DATE = date(2026, 7, 31)


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


def appeal_limitation(order_date: Any, as_on: Any = None,
                      forum: str = "107") -> Dict[str, Any]:
    """
    Whether an appeal is still in time, and for how long.

    `forum` is "107" (first appeal to the Appellate Authority) or "112"
    (appeal to the Appellate Tribunal against the Section 107 order).

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

    tribunal = str(forum or "107").startswith("112")
    today = _as_date(as_on) or date.today()
    caveats = [
        "Time runs from COMMUNICATION of the order, not from its date. "
        "Where the order was uploaded to the portal without separate "
        "service, the date of knowledge is arguable and is often the point "
        "on which a late appeal is admitted."
    ]

    if tribunal:
        ordinary = _add_months(served, APPEAL_WINDOW_MONTHS_112)
        backlog = served < GSTAT_BACKLOG_CUTOFF
        if backlog and GSTAT_BACKLOG_LAST_DATE > ordinary:
            ordinary = GSTAT_BACKLOG_LAST_DATE
        condonable = _add_months(ordinary, APPEAL_CONDONABLE_MONTHS_112)
        period, extra, authority = ("the period for appeal to the Tribunal",
                                    "three further months", "Tribunal")
        bar_clause = "Section 112(6)"
        basis = (
            "Section 112(1) — three months from communication of the order "
            "or the date notified for the Tribunal, whichever is later; "
            "Section 112(6) — three further months on sufficient cause. For "
            "orders communicated before 01.05.2026 the notified last date is "
            "31.07.2026 (S.O. 3502(E) dated 30.06.2026, superseding the "
            "30.06.2026 date for orders before 01.04.2026 in S.O. 4220(E)). Computed in calendar months per section 3(35) of "
            "the General Clauses Act, 1897."
        )
        if backlog:
            caveats.append(
                "This order was communicated before 01.05.2026, so the "
                "notified Tribunal date governs (31.07.2026 on the last "
                "extension known to this module). Confirm no further "
                "extension has been notified. Whether Section 112(6) "
                "condonation runs from the notified date for this cohort is "
                "not settled — treat the condonable date below as arguable, "
                "not assured."
            )
    else:
        ordinary = _add_months(served, APPEAL_WINDOW_MONTHS_107)
        condonable = _add_months(ordinary, APPEAL_CONDONABLE_MONTHS_107)
        period, extra, authority = ("the three-month period",
                                    "one further month", "Appellate Authority")
        bar_clause = "Section 107(4)"
        basis = (
            "Section 107(1) — three months from the date on which the order "
            "is communicated; Section 107(4) — one further month on "
            "sufficient cause. Computed in calendar months per section "
            "3(35) of the General Clauses Act, 1897, not as 90 and 30 days."
        )

    days_left = (ordinary - today).days

    if today <= ordinary:
        status, message = "in_time", (
            f"In time. {days_left} day(s) remain of {period}, "
            f"which expires on {ordinary.strftime('%d.%m.%Y')}."
        )
    elif today <= condonable:
        status, message = "condonable", (
            f"{period[0].upper() + period[1:]} expired on "
            f"{ordinary.strftime('%d.%m.%Y')}. "
            f"The appeal may still be admitted on sufficient cause shown until "
            f"{condonable.strftime('%d.%m.%Y')} — file with an application for "
            "condonation of delay supported by an affidavit."
        )
    else:
        status, message = "time_barred", (
            f"The condonable period expired on "
            f"{condonable.strftime('%d.%m.%Y')}. The {authority} has no "
            f"power to condone beyond {extra} ({bar_clause}); the "
            "remedy, if any, lies in a writ petition. Advise the client "
            "expressly and record the advice."
        )

    return {
        "computed": True,
        "forum": "112" if tribunal else "107",
        "status": status,
        "message": message,
        "order_date": served.isoformat(),
        "as_on": today.isoformat(),
        "ordinary_deadline": ordinary.isoformat(),
        "condonable_deadline": condonable.isoformat(),
        "days_remaining": days_left,
        "basis": basis,
        "caveats": caveats,
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

# The windows are notified, not statutory, and they have CLOSED. The date
# notified under s.128A(1) for payment of the tax is 31.03.2025 (Notification
# No. 21/2024-Central Tax, 08.10.2024), and Rule 164 allows the application in
# SPL-01/SPL-02 within three months of it — 30.06.2025. The one route still
# open is the first proviso to s.128A(1), read with the proviso to Rule
# 164(7): a s.74 notice whose order is redetermined under s.73 on the
# direction of an appellate forum or court (s.75(2)), where the tax is paid,
# and SPL-02 filed, within six months of COMMUNICATION of the redetermination
# order. Earlier revisions reported the waiver as AVAILABLE on
# any s.73 demand for the three years, fifteen months after the window shut.
AMNESTY_PAYMENT_LAST_DATE = date(2025, 3, 31)
AMNESTY_APPLICATION_LAST_DATE = date(2025, 6, 30)
AMNESTY_REDETERMINATION_MONTHS = 6


def amnesty_128a(section: str, tax_period: str,
                 tax_paid: Optional[bool] = None,
                 as_on: Any = None,
                 redetermination_date: Any = None) -> Dict[str, Any]:
    """
    Whether Section 128A is available on this limb.

    Returns eligibility plus the reason, so an ineligible matter carries the
    explanation rather than a bare no — the client asks why, every time.

    `redetermination_date` is the date of COMMUNICATION of an order
    redetermining a s.74 demand under s.73 in pursuance of an appellate
    direction (s.75(2)) — the only case in which the waiver can still be
    claimed after 30.06.2025. It is ignored for any other section: a demand
    that was never under s.74 cannot enter through the proviso.
    """
    today = _as_date(as_on) or date.today()
    redetermined = _as_date(redetermination_date)
    section = _clean_section(section)
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
    elif section.startswith("74") and redetermined is None:
        eligible = False
        reason = (
            "Section 128A applies only to demands under Section 73. This "
            "demand is under Section 74 (fraud, wilful misstatement or "
            "suppression), which is outside the waiver."
        )
        if period in AMNESTY_YEARS:
            reason += (
                " Where the s.74 invocation is contested and the ingredients "
                "are not made out, a re-characterisation to s.73 — an "
                "appellate direction to redetermine the demand under s.73 "
                "(Section 75(2)) — brings it within the "
                "proviso to Section 128A(1), with six months from the "
                "redetermination order to pay and apply — a reason to contest "
                "the characterisation, not merely the quantum."
            )
        reasons.append(reason)
    elif section.startswith("74"):
        # Redetermined under s.73 on an appellate direction: within the
        # proviso to s.128A(1), and handled with its own window below.
        pass
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

    window_open = True
    if eligible:
        if redetermined is not None and section.upper().startswith("74") \
                and not section.upper().startswith("74A"):
            window_close = _add_months(redetermined,
                                       AMNESTY_REDETERMINATION_MONTHS)
            window_open = today <= window_close
            reasons.append(
                f"Redetermined under Section 73 by order communicated on "
                f"{redetermined.strftime('%d.%m.%Y')} on an appellate "
                "direction (Section 75(2)): under the first proviso to "
                "Section 128A(1) read with the proviso to Rule 164(7), the "
                "tax must be paid, and SPL-02 filed, within six months of "
                f"communication of that order — by "
                f"{window_close.strftime('%d.%m.%Y')}."
                + ("" if window_open else " That period has expired.")
            )
        elif today > AMNESTY_APPLICATION_LAST_DATE:
            window_open = False
            reasons.append(
                "Within Section 128A by section and year, but the window has "
                "CLOSED. The tax had to be paid by 31.03.2025 (Notification "
                "No. 21/2024-Central Tax) and the application filed by "
                "30.06.2025 (Rule 164). The waiver cannot now be claimed "
                "unless an application was filed in time — check the portal "
                "for an SPL-01/SPL-02 already on record. The only later route "
                "is a Section 74 demand redetermined under Section 73 on an "
                "appellate direction."
            )
        if not window_open:
            eligible = False

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
        "window_open": window_open,
        "form": "SPL-01 (where a notice or statement has issued but no "
                "order) or SPL-02 (where an order has been passed)",
        "caveats": [
            "The waiver does not extend to any amount payable on account of "
            "an erroneous refund (Section 128A), and interest or penalty "
            "already paid is not refunded.",
            "Section 128A requires withdrawal of any appeal or writ against "
            "the same demand as a condition of the waiver. Weigh this against "
            "the strength of the contested limbs before applying.",
            "Dates applied: tax paid by 31.03.2025, application by "
            "30.06.2025, or six months from a Section 75(2) redetermination "
            "order. These are notified dates; confirm none has been extended "
            "or reopened and that the dates currently in force match before "
            "advising.",
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
    section = _clean_section(intake.get("section_invoked"))
    period = intake.get("tax_period")
    notice_date = intake.get("notice_date")
    limbs = intake.get("defects") or []

    tax_total = 0.0
    head_totals: Dict[str, float] = {}
    for limb in limbs:
        if not isinstance(limb, dict):
            continue
        heads = limb.get("amount_by_head") or {}
        if not isinstance(heads, dict):
            continue
        for head, raw in heads.items():
            value = _num(raw)
            if value:
                key = str(head).strip().lower()
                head_totals[key] = head_totals.get(key, 0.0) + value
                tax_total += value
    if not tax_total:
        tax_total = _num(intake.get("amount_disputed")) or 0.0
        head_totals = {"unallocated": tax_total} if tax_total else {}

    # Which date is the SHOW CAUSE NOTICE? Only a DRC-01 is one. A DRC-07 is
    # the order — counting the s.73(8) window from it printed a concession
    # deadline that never existed. A DRC-01A, ASMT-10, ADT-02 or any other
    # intimation precedes the SCN, so the cheapest stage — before the notice —
    # is still open, and dating the 30-day window from the intimation told
    # the partner the dearer stage was running. An explicit `scn_date` always
    # wins.
    form = str(intake.get("notice_type") or "").upper().replace(" ", "")
    is_order = form.startswith("DRC-07")
    is_scn = form in ("", "DRC-01")
    order_date = intake.get("order_date") or (notice_date if is_order else None)
    scn_date = intake.get("scn_date") or (notice_date if is_scn else None)

    penalty = penalty_options(section, tax_total, scn_date,
                              fraud=intake.get("fraud_established"),
                              order_date=order_date)
    if penalty.get("computed") and not is_order and not is_scn \
            and not intake.get("scn_date"):
        penalty["caveats"].insert(0,
            f"The document on file ({form}) is not a show cause notice, so no "
            "SCN has issued and the BEFORE-NOTICE stage is still open — nil "
            "penalty under Sections 73(5) and 74A(8)(i), 15% under Sections "
            "74(5) and 74A(9)(i). It is the cheapest stage; advise on it "
            "before the SCN issues.")
    if penalty.get("computed") and order_date:
        penalty["caveats"].append(
            "Post-order concessions run from COMMUNICATION of the order. The "
            "date used is the order's own date unless a later date of "
            "communication has been recorded as order_date.")

    computations: Dict[str, Any] = {
        "penalty": penalty,
        "amnesty_128a": amnesty_128a(
            section, period, intake.get("tax_paid"),
            redetermination_date=intake.get("redetermination_date")),
    }

    if order_date:
        computations["appeal_limitation"] = appeal_limitation(order_date)
        computations["predeposit_107"] = predeposit_by_head(head_totals, "107")

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
