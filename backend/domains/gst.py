"""GST domain pack.

Holds the stable anchors — statutory sections, notice-form codes, procedural
doctrines, the state -> High Court map, the defect catalogue and the curated
authorities.

ON CASE CITATIONS
-----------------
This file once carried a rule that no case citation would ever be hardcoded,
because case law is volatile and mis-citing it is the largest professional risk
here. That reasoning still holds; the conclusion drawn from it did not. A panel
told to generate its own authorities, with a verifier that downgrades anything
doubtful, produced replies carrying no case law at all — which is not the safe
outcome, merely a poor one.

Curated authorities now live in `gst_authorities.py`, and the safety property
is enforced where it belongs: verification runs on every citation from every
source, and nothing that fails it reaches the filing document. See that file
for the full reasoning.
"""

import re

from .gst_authorities import (  # noqa: F401  (re-exported as pack interface)
    AUTHORITIES,
    authorities_brief,
    authorities_for_defect,
    authorities_for_tags,
)
from .gst_defects import (  # noqa: F401  (re-exported as pack interface)
    DEFECT_TYPES,
    DEFECT_TYPES_BY_KEY,
    HEARING_QUESTIONS,
    defect_type,
    evidence_for,
    hearing_questions_for,
)

NAME = "Goods and Services Tax"
SHORT_NAME = "GST"
DEPARTMENT = "the proper officer / GST department"
TAXPAYER_TERM = "the registered person"

# --------------------------------------------------------------------------
# Notice types
# --------------------------------------------------------------------------


class NoticeType:
    def __init__(self, code, name, statute, description, typical_issues,
                 reply_form=None, deadline_note=None):
        self.code = code
        self.name = name
        self.statute = statute
        self.description = description
        self.typical_issues = typical_issues
        self.reply_form = reply_form
        self.deadline_note = deadline_note

    def as_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "statute": self.statute,
            "description": self.description,
            "typical_issues": self.typical_issues,
            "reply_form": self.reply_form,
            "deadline_note": self.deadline_note,
        }


NOTICE_TYPES = {
    n.code: n for n in [
        NoticeType(
            "ASMT-10", "Scrutiny of returns — notice of discrepancy",
            "Section 61 read with Rule 99",
            "Officer has scrutinised returns and communicated discrepancies.",
            ["GSTR-3B vs GSTR-1 mismatch", "GSTR-3B vs GSTR-2A/2B ITC mismatch",
             "turnover variance vs financials", "e-way bill vs returns variance",
             "RCM short payment", "interest under s.50"],
            reply_form="ASMT-11",
            deadline_note="Reply generally within 30 days of service unless extended.",
        ),
        NoticeType(
            "DRC-01A", "Intimation of tax ascertained as payable (pre-SCN)",
            "Section 73(5)/74(5) read with Rule 142(1A)",
            "Pre-show-cause intimation inviting voluntary payment before a formal SCN.",
            ["quantification disputes", "opportunity to pay with reduced penalty",
             "whether ingredients of s.74 are made out"],
            reply_form="DRC-01A Part B",
        ),
        NoticeType(
            "DRC-01", "Show cause notice — determination of tax",
            "Section 73 / 74 / 74A read with Rule 142(1)",
            "Formal SCN proposing demand of tax, interest and penalty.",
            ["ITC ineligibility", "suppression allegations", "classification",
             "valuation", "place of supply", "limitation", "s.74 invoked without fraud"],
            reply_form="DRC-06",
            deadline_note="Reply within the period stated in the SCN; personal hearing "
                          "under s.75(4) must be granted where requested or where an "
                          "adverse order is contemplated.",
        ),
        NoticeType(
            "DRC-07", "Summary of order — demand confirmed",
            "Section 73/74 read with Rule 142(5)",
            "Order confirming demand. Next step is appeal under s.107.",
            ["order travelling beyond the SCN (s.75(7))", "non-speaking order",
             "hearing not granted", "pre-deposit computation", "limitation for appeal"],
            reply_form="APL-01 (appeal)",
            deadline_note="Appeal under s.107 within 3 months, condonable by 1 further "
                          "month, with 10% pre-deposit of disputed tax.",
        ),
        NoticeType(
            "ADT-01", "Notice for conduct of audit",
            "Section 65 read with Rule 101",
            "Departmental audit of the registered person's records.",
            ["records to be produced", "period selected", "scope of audit",
             "adequacy of 15-day notice"],
        ),
        NoticeType(
            "ADT-02", "Audit report — findings communicated",
            "Section 65(6) read with Rule 101(5)",
            "Audit findings that typically precede a DRC-01A/DRC-01.",
            ["ITC reversals proposed", "turnover reconciliation",
             "RCM liabilities", "classification disputes"],
        ),
        NoticeType(
            "RFD-08", "Show cause notice for rejection of refund",
            "Section 54 read with Rule 92(3)",
            "Proposed rejection of a refund claim.",
            ["inverted duty structure computation", "zero-rated supply refunds",
             "unjust enrichment", "limitation under s.54(1)", "deficiency memos"],
            reply_form="RFD-09",
            deadline_note="Reply in RFD-09 within 15 days of service.",
        ),
        NoticeType(
            "REG-17", "Show cause notice for cancellation of registration",
            "Section 29 read with Rule 22",
            "Proposed cancellation of GST registration.",
            ["non-filing of returns", "alleged non-existence at principal place",
             "fraudulent registration allegations", "revocation route under s.30"],
            reply_form="REG-18",
            deadline_note="Reply within 7 working days of service.",
        ),
        NoticeType(
            "DRC-01C", "Intimation of ITC difference (2B vs 3B)",
            "Rule 88D",
            "System-generated intimation of ITC availed in excess of GSTR-2B.",
            ["2B vs 3B reconciliation", "timing differences", "amendments and credit notes"],
            reply_form="DRC-01C Part B",
        ),
        NoticeType(
            "MOV-07", "Notice for detention of goods in transit",
            "Section 129 read with Rule 138",
            "Detention of goods/conveyance during movement.",
            ["e-way bill expiry or absence", "clerical errors in e-way bill",
             "intent to evade — whether established", "quantum of penalty under s.129(1)"],
            deadline_note="Time-critical: goods remain detained pending resolution.",
        ),
        # -- Scrutiny and assessment --------------------------------------
        NoticeType(
            "ASMT-11", "Reply to scrutiny notice",
            "Section 61(2) read with Rule 99(2)",
            "The registered person's explanation to an ASMT-10.",
            ["as raised in the ASMT-10"],
            reply_form="ASMT-11",
        ),
        NoticeType(
            "ASMT-12", "Acceptance of explanation — proceedings dropped",
            "Section 61(3) read with Rule 99(3)",
            "Order closing scrutiny where the explanation is found acceptable.",
            ["closure of the scrutiny", "limbs dropped and limbs surviving"],
        ),
        NoticeType(
            "ASMT-13", "Assessment of non-filers — best judgment",
            "Section 62 read with Rule 100(1)",
            "Best judgment assessment where the return was not furnished.",
            ["withdrawal on filing within 30 days under s.62(2)",
             "quantification without material", "service of the s.46 notice"],
            reply_form="Return under s.62(2)",
            deadline_note="Order stands withdrawn if the valid return is filed "
                          "within 30 days of service, with interest and late fee.",
        ),
        NoticeType(
            "ASMT-14", "Assessment of unregistered persons",
            "Section 63 read with Rule 100(2)",
            "Assessment of a taxable person who failed to obtain registration.",
            ["liability to register", "period of liability", "quantification"],
            reply_form="ASMT-15",
        ),

        # -- Demand, recovery and payment ---------------------------------
        NoticeType(
            "DRC-01B", "Intimation of liability difference (GSTR-1 vs 3B)",
            "Rule 88C",
            "System intimation where GSTR-1 liability exceeds GSTR-3B payment.",
            ["timing of payment", "amendments", "credit notes",
             "blocking of GSTR-1 on non-response"],
            reply_form="DRC-01B Part B",
        ),
        NoticeType(
            "DRC-03", "Voluntary payment / payment against a notice",
            "Section 73(5)/74(5) read with Rule 142(2)/(3)",
            "Challan by which tax, interest or penalty is discharged.",
            ["pre-notice payment foreclosing penalty",
             "payment made under protest", "appropriation via DRC-03A"],
        ),
        NoticeType(
            "DRC-06", "Reply to a show cause notice",
            "Rule 142(4)",
            "The registered person's reply to a DRC-01.",
            ["as raised in the DRC-01"],
            reply_form="DRC-06",
        ),
        NoticeType(
            "DRC-13", "Notice to a third person for recovery",
            "Section 79(1)(c) read with Rule 145",
            "Garnishee notice to a debtor of the defaulter.",
            ["whether any amount is due", "stay of the underlying demand",
             "pre-deposit already made"],
            reply_form="DRC-14 / representation",
            deadline_note="Time-critical: bank accounts and receivables are "
                          "attached pending resolution.",
        ),

        # -- Appeals -------------------------------------------------------
        NoticeType(
            "APL-01", "Appeal to the Appellate Authority",
            "Section 107 read with Rule 108",
            "First appeal against an order.",
            ["limitation from communication", "10% pre-deposit from the cash "
             "ledger", "grounds not taken below", "condonation of delay"],
            reply_form="APL-01",
            deadline_note="3 months from communication, condonable by 1 further "
                          "month. Pre-deposit 10% of disputed tax (10% of "
                          "penalty where the demand is penalty only), capped, "
                          "and payable from the Electronic Cash Ledger only.",
        ),
        NoticeType(
            "APL-05", "Appeal to the Appellate Tribunal (GSTAT)",
            "Section 112 read with Rule 110",
            "Second appeal to the GST Appellate Tribunal.",
            ["additional 10% pre-deposit (20% cumulative)",
             "limitation and the backlog window", "questions of law"],
            reply_form="APL-05",
            deadline_note="GSTAT has been operational since 24 September 2025. "
                          "Verify the current filing window and the backlog "
                          "cut-off applicable to orders communicated before "
                          "01.04.2026 before advising on limitation.",
        ),

        # -- Audit, refund, registration -----------------------------------
        NoticeType(
            "ADT-04", "Special audit directed",
            "Section 66 read with Rule 102",
            "Audit by a nominated chartered or cost accountant.",
            ["prior approval of the Commissioner", "nature and complexity "
             "threshold", "opportunity of hearing before direction"],
        ),
        NoticeType(
            "RFD-06", "Refund sanction / rejection order",
            "Section 54 read with Rule 92",
            "Order sanctioning or rejecting a refund claim.",
            ["reasons for rejection", "interest under s.56",
             "appeal under s.107"],
            reply_form="APL-01 (appeal)",
        ),
        NoticeType(
            "REG-03", "Notice seeking clarification on a registration application",
            "Rule 9(2)",
            "Query on a fresh registration or amendment application.",
            ["documents sought", "principal place of business",
             "physical verification"],
            reply_form="REG-04",
            deadline_note="Reply in REG-04 within 7 working days.",
        ),
        NoticeType(
            "REG-23", "Show cause notice — revocation of cancellation",
            "Rule 23(3)",
            "Proposed rejection of an application to revoke cancellation.",
            ["returns and dues cleared", "reasons for the original cancellation"],
            reply_form="REG-24",
        ),
        NoticeType(
            "REG-31", "Intimation of suspension of registration",
            "Rule 21A",
            "Suspension pending cancellation proceedings.",
            ["significant differences alleged", "reply within 30 days",
             "restoration on compliance"],
        ),

        # -- Movement of goods ---------------------------------------------
        NoticeType(
            "MOV-06", "Order of detention of goods and conveyance",
            "Section 129(1) read with Rule 140",
            "Formal detention order following interception.",
            ["intent to evade", "clerical e-way bill defects",
             "quantum under s.129(1)(a)/(b)"],
            reply_form="MOV-09 representation",
            deadline_note="Time-critical: goods remain detained.",
        ),
        NoticeType(
            "MOV-09", "Order of demand of tax and penalty",
            "Section 129(3)",
            "Penalty order after detention.",
            ["mens rea", "proportionality", "appeal under s.107"],
            reply_form="APL-01 (appeal)",
        ),
        NoticeType(
            "MOV-10", "Notice for confiscation",
            "Section 130 read with Rule 141",
            "Proposed confiscation of goods and conveyance.",
            ["ingredients of s.130 as distinct from s.129",
             "option to pay fine in lieu of confiscation"],
            deadline_note="Time-critical and severe: confiscation is a distinct "
                          "and higher threshold than detention.",
        ),

        # -- Other proceedings ----------------------------------------------
        NoticeType(
            "SUMMONS-70", "Summons under Section 70",
            "Section 70",
            "Summons to give evidence or produce documents.",
            ["scope of the summons", "right against self-incrimination",
             "presence of an authorised representative", "record of statement"],
            deadline_note="Attendance is compulsory. Non-appearance carries "
                          "consequences under s.122 and the Code.",
        ),
        NoticeType(
            "SPL-01", "Amnesty application — waiver of interest and penalty",
            "Section 128A",
            "Application for waiver on demands for FY 2017-18 to 2019-20.",
            ["full tax paid within the notified window",
             "withdrawal of appeals as a condition", "scope of the waiver"],
            reply_form="SPL-01 / SPL-02",
            deadline_note="Verify the operative dates before relying on this "
                          "route — the window has moved more than once.",
        ),
        NoticeType(
            "ARA-01", "Application for advance ruling",
            "Section 97 read with Rule 104",
            "Application to the Authority for Advance Ruling.",
            ["admissibility of the question", "pendency bar under the proviso "
             "to s.98(2)", "binding only on the applicant and the officer"],
        ),
        NoticeType(
            "OTHER", "Other GST communication",
            "As specified in the notice",
            "Any other GST notice, summons or communication.",
            ["as raised in the notice"],
        ),
    ]
}

# --------------------------------------------------------------------------
# Statutory anchors injected into every panel prompt
# --------------------------------------------------------------------------

STATUTORY_FRAMEWORK = """\
STABLE STATUTORY ANCHORS (CGST Act, 2017 unless stated):

Input tax credit
- s.16(2) cumulative conditions: (a) tax invoice/debit note; (aa) invoice
  furnished by supplier and communicated in GSTR-2B; (b) receipt of goods or
  services; (c) tax actually paid to Government by the supplier; (d) return
  under s.39 furnished by the recipient.
- s.16(4) time limit for availment; s.16(5) and s.16(6) provide retrospective
  relief for specified years and for revoked/restored registrations (inserted
  by the Finance (No. 2) Act, 2024) — check applicability to the years in issue.
- s.17(5) blocked credits. Rule 37 (180-day non-payment reversal);
  Rules 42/43 (common credit); Rule 86A (blocking of electronic credit ledger);
  Rule 86B (1% cash restriction); Rules 88C/88D (mismatch intimations).

Demands and limitation
- s.73 (other than fraud): limitation runs from the due date of the annual
  return for the financial year; order within 3 years.
- s.74 (fraud, wilful misstatement or suppression of facts): 5 years. The
  ingredients must be specifically alleged AND established — mechanical
  invocation of s.74 to enlarge limitation is a recognised ground of challenge.
- s.74A applies from FY 2024-25 with a common limitation scheme.
- s.168A extensions of limitation have themselves been the subject of
  challenge; verify the position applicable to the year in issue.

Procedure and natural justice
- s.75(4): opportunity of personal hearing where requested in writing or where
  an adverse decision is contemplated.
- s.75(7): the demand confirmed cannot exceed the amount, nor rest on grounds
  other than those, specified in the show cause notice.
- s.169: modes of service. Portal-only upload under the "Additional Notices"
  tab has been a live litigation ground.
- Rule 142(1A): DRC-01A intimation before issue of DRC-01.

Interest, penalty, amnesty
- s.50 interest; s.50(3) for ITC wrongly availed and utilised.
- s.122 / s.125 penalties; s.126 general disciplines.
- s.128A amnesty: waiver of interest and penalty for s.73 demands for
  FY 2017-18, 2018-19 and 2019-20 subject to payment of full tax within the
  notified window (Forms SPL-01/SPL-02). Verify current dates before relying.

Appeals
- s.107: Appellate Authority — 3 months, condonable by 1 month, 10% pre-deposit.
- s.112: GST Appellate Tribunal — further pre-deposit; GSTAT became
  operational in September 2025. Verify current filing procedure and dates.
"""

PROCEDURAL_GROUNDS = """\
PROCEDURAL AND JURISDICTIONAL GROUNDS — check every one of these before
arguing merits, because a matter is more often won here than on substance:

1.  Limitation — is the SCN/order within the s.73/74/74A period? Was s.74
    invoked only to enlarge limitation, without the ingredients being alleged
    with particulars?
2.  Jurisdiction of the proper officer — monetary limits and assignment of
    functions; Central vs State jurisdiction and cross-empowerment.
3.  DRC-01A — was the pre-SCN intimation issued at all? Rule 142(1A).
4.  Vagueness of the SCN — does it disclose the specific allegation, the
    provision invoked, and the basis of quantification? A notice that merely
    annexes a table of differences is vulnerable.
5.  Personal hearing — s.75(4). Was one granted, and was it meaningful
    (adequate notice, adjournments, hearing before a different officer)?
6.  Order beyond the SCN — s.75(7): new grounds or enhanced amounts.
7.  Non-speaking order — were the replies and submissions considered and dealt
    with, or reproduced and brushed aside?
8.  Service — s.169. Was the notice actually communicated, or only uploaded
    under a tab the taxpayer had no reason to monitor?
9.  Mechanical reliance on system-generated data (2A/2B, e-way bill) without
    independent application of mind.
10. Retrospective or clarificatory circulars applied to past periods.
"""

# --------------------------------------------------------------------------
# Jurisdiction: state -> High Court (binding vs persuasive weighting)
# --------------------------------------------------------------------------

STATE_HIGH_COURT = {
    "Andhra Pradesh": "High Court of Andhra Pradesh",
    "Arunachal Pradesh": "Gauhati High Court",
    "Assam": "Gauhati High Court",
    "Bihar": "Patna High Court",
    "Chhattisgarh": "Chhattisgarh High Court",
    "Delhi": "Delhi High Court",
    "Goa": "Bombay High Court (Goa Bench)",
    "Gujarat": "Gujarat High Court",
    "Haryana": "Punjab and Haryana High Court",
    "Himachal Pradesh": "Himachal Pradesh High Court",
    "Jammu and Kashmir": "High Court of Jammu & Kashmir and Ladakh",
    "Jharkhand": "Jharkhand High Court",
    "Karnataka": "High Court of Karnataka",
    "Kerala": "Kerala High Court",
    "Ladakh": "High Court of Jammu & Kashmir and Ladakh",
    "Madhya Pradesh": "Madhya Pradesh High Court",
    "Maharashtra": "Bombay High Court",
    "Manipur": "Manipur High Court",
    "Meghalaya": "Meghalaya High Court",
    "Mizoram": "Gauhati High Court",
    "Nagaland": "Gauhati High Court",
    "Odisha": "Orissa High Court",
    "Puducherry": "Madras High Court",
    "Punjab": "Punjab and Haryana High Court",
    "Chandigarh": "Punjab and Haryana High Court",
    "Rajasthan": "Rajasthan High Court",
    "Sikkim": "Sikkim High Court",
    "Tamil Nadu": "Madras High Court",
    "Telangana": "High Court for the State of Telangana",
    "Tripura": "Tripura High Court",
    "Uttar Pradesh": "Allahabad High Court",
    "Uttarakhand": "Uttarakhand High Court",
    "West Bengal": "Calcutta High Court",
    "Andaman and Nicobar Islands": "Calcutta High Court",
    "Dadra and Nagar Haveli and Daman and Diu": "Bombay High Court",
    "Lakshadweep": "Kerala High Court",
}

STATES = sorted(STATE_HIGH_COURT.keys())


def jurisdiction_brief(state: str) -> str:
    """Prompt fragment telling the panel which precedent binds this matter."""
    if not state or state not in STATE_HIGH_COURT:
        return (
            "JURISDICTION: not specified. Treat all High Court authority as "
            "persuasive only, and say so explicitly wherever it matters."
        )
    hc = STATE_HIGH_COURT[state]
    return f"""\
JURISDICTION: {state}. The jurisdictional High Court is the {hc}.

Precedent weighting you MUST apply:
- Supreme Court decisions bind everywhere.
- {hc} decisions BIND the proper officer in {state}. Lead with them.
- Decisions of other High Courts are PERSUASIVE ONLY. If you rely on one, say
  so in terms, and check whether {hc} has taken a contrary view — if it has,
  that contrary view governs this matter and must be confronted, not ignored.
- AAR/AAAR rulings bind only the applicant and the jurisdictional officer in
  that case. Treat them as indicative.
- Where the group operates in several States, flag expressly that the position
  may differ across registrations and that a uniform group position may not be
  available.
"""


# --------------------------------------------------------------------------
# Citation patterns for the verification layer
# --------------------------------------------------------------------------

CITATION_PATTERNS = [
    # Reported case citations: (2023) 45 GSTL 123, [2024] 160 taxmann.com 78
    re.compile(
        r"[\(\[]\s*\d{4}\s*[\)\]]\s*\d+\s+"
        r"(?:GSTL|STR|ELT|ITR|SCC|TAXMANN\.COM|taxmann\.com|VST|GST|TMI)\s+\d+",
        re.IGNORECASE,
    ),
    # AIR 2019 SC 456 style
    re.compile(r"\bAIR\s+\d{4}\s+[A-Z]{2,4}\s+\d+", re.IGNORECASE),
    # Case name followed by a court hint: "X v. Y (Delhi HC)" / "X vs Union of India"
    re.compile(
        r"\b[A-Z][\w&.,'\- ]{2,60}?\s+v(?:s?\.?|ersus)\s+[A-Z][\w&.,'\- ]{2,60}?"
        r"(?=[,\(\[]|\s+\d{4}|\s*$)",
    ),
    # Writ / appeal numbers
    re.compile(
        r"\b(?:W\.?P\.?|Writ Petition|C\.?A\.?|Civil Appeal|SLP|TS)\s*"
        r"(?:\(C\)|\(Civil\))?\s*(?:No\.?)?\s*\d+[\d/\-]*\s*(?:of\s*\d{4})?",
        re.IGNORECASE,
    ),
    # Circulars and notifications
    re.compile(
        r"\b(?:Circular|Notification|Instruction)\s+No\.?\s*"
        r"[\d]+[\w/\-.]*(?:\s*[-–]\s*(?:CT|IT|GST|Central Tax)[\w()/ \-]*)?"
        r"(?:\s*dated\s+[\d.\-/]+)?",
        re.IGNORECASE,
    ),
]

# Statutory references are checkable against the Act itself rather than case law
SECTION_PATTERN = re.compile(
    r"\b(?:[Ss]ection|[Ss]ec\.?|u/s|[Rr]ule)\s*\d+[A-Za-z]?"
    r"(?:\s*\(\s*\w+\s*\))*",
)


def intake_schema() -> dict:
    """Fields the UI collects for a GST matter."""
    return {
        "domain": "gst",
        "notice_types": [n.as_dict() for n in NOTICE_TYPES.values()],
        "states": STATES,
        "fields": [
            {"key": "notice_type", "label": "Notice type", "type": "select",
             "required": True},
            {"key": "state", "label": "State / jurisdiction", "type": "select",
             "required": True,
             "help": "Determines which High Court binds the proper officer."},
            {"key": "tax_period", "label": "Tax period / FY", "type": "text",
             "required": True, "placeholder": "e.g. FY 2019-20, or Apr-Jun 2021"},
            {"key": "section_invoked", "label": "Section invoked in the notice",
             "type": "text", "placeholder": "e.g. 73, 74, 61"},
            {"key": "amount_disputed", "label": "Amount in dispute (INR)",
             "type": "number"},
            {"key": "notice_date", "label": "Date of notice", "type": "date"},
            {"key": "due_date", "label": "Reply due date", "type": "date"},
            {"key": "issues", "label": "Issues raised by the department",
             "type": "textarea", "required": True,
             "placeholder": "One issue per line, as framed in the notice."},
            {"key": "facts", "label": "Facts and background", "type": "textarea",
             "required": True,
             "placeholder": "Nature of business, what actually happened, what "
                            "records exist, any prior correspondence."},
            {"key": "documents_available", "label": "Documents available",
             "type": "textarea",
             "placeholder": "Invoices, ledgers, reconciliations, contracts, "
                            "e-way bills, bank statements..."},
            {"key": "client_name", "label": "Client name", "type": "text",
             "sensitive": True},
            {"key": "gstin", "label": "GSTIN", "type": "text", "sensitive": True},
        ],
    }


# --------------------------------------------------------------------------
# Reconciliation buckets
#
# A 2A/3B difference is not one number, it is several problems wearing one
# number. Each category carries a DIFFERENT legal argument and a different
# prospect of success, and a reply that argues the aggregate concedes ground
# it did not need to concede.
#
# The order here matters: classification tries each bucket in turn, so the
# unambiguous mechanical categories (RCM, imports, ISD) are tested before the
# judgement-dependent ones.
# --------------------------------------------------------------------------


class ReconBucket:
    def __init__(self, key, label, keywords, strength, position, action):
        self.key = key
        self.label = label
        self.keywords = keywords
        self.strength = strength      # strong | defensible | weak | concede
        self.position = position      # the argument for this bucket
        self.action = action          # what the reply does with it

    def as_dict(self):
        return {"key": self.key, "label": self.label, "strength": self.strength,
                "position": self.position, "action": self.action}


RECONCILIATION_BUCKETS = [
    ReconBucket(
        "rcm", "Reverse charge — not expected in GSTR-2A",
        ["rcm", "reverse charge", "self invoice", "section 9(3)", "section 9(4)"],
        "strong",
        "Tax paid under reverse charge is self-assessed and discharged by the "
        "recipient. It appears in GSTR-3B by design and has no counterpart in "
        "GSTR-2A. It is not a mismatch and its inclusion in the notice is an "
        "error of comparison.",
        "Excluded from the demand at the threshold.",
    ),
    ReconBucket(
        "import_igst", "IGST on imports — not expected in GSTR-2A",
        ["import", "boe", "bill of entry", "customs", "igst on import"],
        "strong",
        "IGST paid on import of goods is availed on the strength of the Bill "
        "of Entry and is reflected in GSTR-2A only through ICEGATE. Absence "
        "from GSTR-2A does not bear on eligibility.",
        "Excluded from the demand at the threshold.",
    ),
    ReconBucket(
        "isd", "ISD credit — distributed, not invoiced",
        ["isd", "input service distributor"],
        "strong",
        "Credit distributed by an Input Service Distributor is availed on an "
        "ISD invoice and reported separately. It is not expected to appear in "
        "the recipient's GSTR-2A as a supplier invoice.",
        "Excluded from the demand at the threshold.",
    ),
    ReconBucket(
        "timing", "Timing — supplier furnished GSTR-1 in a later period",
        ["timing", "later period", "subsequent period", "next month", "filed late",
         "delayed filing", "reflected subsequently", "appears in later",
         "belated", "next quarter"],
        "strong",
        "GSTR-2A is a dynamic statement that updates as suppliers furnish "
        "GSTR-1. Where the supplier has since filed and the credit now appears, "
        "the conditions in section 16(2) were satisfied at the material time "
        "and no reversal arises. The subsequent GSTR-2A is produced in support.",
        "Contested with documentary proof of the later filing.",
    ),
    ReconBucket(
        "amendment", "Amendments and credit notes",
        ["amendment", "amended", "credit note", "debit note", "revised",
         "cdnr", "b2ba"],
        "defensible",
        "The difference arises from amendments or credit notes reflected in "
        "one statement and not the other for the period under comparison. "
        "Reconciled on the documents.",
        "Contested with the amendment trail.",
    ),
    ReconBucket(
        "supplier_error", "Supplier reporting error",
        ["supplier error", "wrong gstin", "reported under", "wrongly reported",
         "b2c instead", "incorrect gstin", "supplier mistake"],
        "defensible",
        "The supplier has reported the supply incorrectly — against another "
        "GSTIN, or as B2C. The recipient has satisfied every condition within "
        "its control under section 16(2), and cannot be visited with the "
        "consequence of the supplier's reporting error.",
        "Contested; supplier confirmation to be obtained.",
    ),
    ReconBucket(
        "non_filer", "Supplier appears not to have furnished GSTR-1",
        ["non filer", "non-filer", "not filed", "supplier not filed",
         "return defaulter", "gstr-1 not filed", "supplier defaulter",
         "cancelled supplier", "registration cancelled"],
        "weak",
        "This is the exposed category. Section 16(2)(c) requires the tax to "
        "have been paid to the Government. Where the supplier has not filed, "
        "the department will press this and the recipient's answer rests on "
        "having satisfied the conditions within its control — a genuine "
        "transaction, an invoice, receipt of the supply, and payment through "
        "banking channels. Establish each on the documents, and consider "
        "whether contesting this portion is commercially worthwhile.",
        "Weakest limb. Documentary proof essential; consider the arithmetic "
        "of contesting versus reversing.",
    ),
    ReconBucket(
        "ineligible", "Ineligible credit under section 17(5)",
        ["ineligible", "blocked", "17(5)", "section 17(5)", "blocked credit",
         "not eligible", "disallowed"],
        "concede",
        "Credit blocked under section 17(5) is not available. Where it has "
        "been availed it should be reversed voluntarily with interest, which "
        "both closes the exposure and supports a plea against penalty.",
        "Reverse voluntarily. Do not contest.",
    ),
    ReconBucket(
        "clerical", "Clerical or data entry difference",
        ["clerical", "data entry", "typo", "rounding", "keying error",
         "posting error", "duplicate"],
        "defensible",
        "A recording difference rather than a credit issue. Reconciled on the "
        "books and corrected.",
        "Explained with the corrected working.",
    ),
]

RECONCILIATION_BUCKETS_BY_KEY = {b.key: b for b in RECONCILIATION_BUCKETS}

# Anything that matches nothing above. Deliberately named so it cannot be
# read as benign: an unexplained difference is the part of the demand with no
# argument behind it, and the reply must not pretend otherwise.
UNRECONCILED = ReconBucket(
    "unreconciled", "Not yet reconciled",
    [],
    "weak",
    "This portion has not been explained. Until it is traced to a category it "
    "must be treated as unsupported, and the reply should not assert a "
    "position on it.",
    "Trace before filing, or concede this portion.",
)


def reconciliation_brief(summary: dict) -> str:
    """
    Render a bucketed reconciliation for the panel.

    Only aggregates travel: bucket totals, counts, and the strength of each
    position. Invoice-level data never leaves the machine, which keeps this at
    a few hundred tokens instead of hundreds of thousands.
    """
    if not summary or not summary.get("buckets"):
        return ""

    lines = [
        "RECONCILIATION OF THE DIFFERENCE (from the taxpayer's own records):",
        "",
        f"Total difference analysed: Rs. {summary['total']:,.0f} "
        f"across {summary['row_count']} line(s).",
        "",
    ]
    for entry in summary["buckets"]:
        bucket = RECONCILIATION_BUCKETS_BY_KEY.get(entry["key"], UNRECONCILED)
        lines.append(
            f"- {bucket.label}: Rs. {entry['amount']:,.0f} "
            f"({entry['count']} line(s), {entry['share']:.0%} of the difference) "
            f"— position: {bucket.strength.upper()}"
        )
        lines.append(f"    {bucket.position}")
        lines.append("")

    lines += [
        "HOW TO USE THIS:",
        "Argue each category on its own footing and quantify it. A reply that "
        "meets the difference as a single figure concedes ground it need not "
        "concede — the mechanical categories fall away at the threshold, the "
        "timing difference is answered on documents, and only the residue is "
        "genuinely in issue. Where a category is weak or unreconciled, say so "
        "to the signing partner rather than papering over it.",
    ]
    return "\n".join(lines)
