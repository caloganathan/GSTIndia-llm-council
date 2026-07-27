"""Curated GST authorities, indexed by defect type.

WHY THIS FILE EXISTS, HAVING BEEN FORBIDDEN
-------------------------------------------
The original design rule was "never hardcode case citations", on the reasoning
that case law is volatile and mis-citing it is the single biggest professional
risk in this product. The reasoning was right. The rule was wrong, and the
evidence that falsified it is a reply pack the product actually produced: nine
authorities, eight of them bare statutory sections, one case — carried as
"light support" and marked *to be confirmed*. A reply with no authority is not
safer than a reply with a wrong one. It is simply a worse reply, filed under
the firm's name.

Meanwhile the limb of the real matter that turned on law was won on two
authorities that had been sitting in the partner's own drafting skill the whole
time: Safari Retreats in the Supreme Court, and CBIC Circular 172/04/2022-GST.
Neither is volatile. Both decide the point.

THE RULE THAT REPLACES IT
-------------------------
1.  The library is a STARTING POINT, never an output. Nothing here is quoted
    into a document on the strength of being in this file.
2.  Every entry is put through the verification layer against live sources on
    every run, exactly as a model-generated citation is.
3.  An authority that does not come back VERIFIED never reaches the filing
    document. It goes to the internal file note with a confirm-before-filing
    flag, where a caveat belongs.

That inverts the old failure mode. Previously the reply carried no law and the
schedule of authorities carried the caveats. Now the reply carries only what
was verified, and the caveats stay in the office.

CERTAINTY
---------
`certainty` records where an entry came from, and is NOT a substitute for
verification:

    "filed"    appears in a reply this firm has filed and which the department
               accepted on that limb. The citation form is the one that was
               actually put in front of an officer.
    "library"  curated from the firm's drafting reference. Sound starting
               points; the citation form has not been independently confirmed
               here and must be checked before use.
"""

from typing import Any, Dict, Iterable, List

FILED = "filed"
LIBRARY = "library"

CASE = "case"
CIRCULAR = "circular"
NOTIFICATION = "notification"
STATUTE = "statute"


class Authority:
    def __init__(self, citation, proposition, tags, kind=CASE, forum="",
                 certainty=LIBRARY, note=""):
        self.citation = citation
        self.proposition = proposition
        self.tags = list(tags)
        self.kind = kind
        self.forum = forum
        self.certainty = certainty
        self.note = note

    def as_dict(self) -> Dict[str, Any]:
        return {
            "citation": self.citation,
            "proposition": self.proposition,
            "forum": self.forum,
            "kind": self.kind,
            "certainty": self.certainty,
            "note": self.note,
            "tags": self.tags,
        }


AUTHORITIES: List[Authority] = [

    # -- Blocked credit and works contract --------------------------------
    Authority(
        "M/s Safari Retreats Pvt. Ltd. v. Chief Commissioner of Central GST, "
        "Civil Appeal No. 2948 of 2023, decided 03.10.2024",
        "Input tax credit on construction inputs is not blocked where the "
        "construction serves a plant-and-machinery or business purpose; the "
        "functional test of business use governs Section 17(5)(d).",
        ["itc_blocked_17_5", "works_contract"],
        forum="Supreme Court", certainty=FILED,
        note="Cited in this form in a reply accepted by the proper officer on "
             "the Section 17(5) limb.",
    ),
    Authority(
        "CBIC Circular No. 172/04/2022-GST dated 06.07.2022",
        "Input tax credit on goods and services used by a contractor for "
        "construction supplied as a works contract to another registered "
        "person is not blocked under Section 17(5)(c)/(d). The bar reaches "
        "construction on the taxpayer's OWN account, not construction supplied "
        "onward as a taxable works contract.",
        ["itc_blocked_17_5", "works_contract"],
        kind=CIRCULAR, forum="CBIC", certainty=FILED,
        note="Decisive on the works-contract limb; a circular binds the "
             "department even where it does not bind the assessee.",
    ),
    Authority(
        "Section 2(119), CGST Act, 2017",
        "Defines works contract as a contract for building, construction, "
        "commissioning, installation, fitting out, improvement, alteration, "
        "repair, maintenance or renovation of immovable property where "
        "transfer of property in goods is involved.",
        ["itc_blocked_17_5", "works_contract"],
        kind=STATUTE, certainty=FILED,
    ),
    Authority(
        "Section 17(5)(a), CGST Act, 2017",
        "The motor-vehicle bar reaches vehicles for transportation of PERSONS "
        "with approved seating capacity of not more than thirteen. Vehicles "
        "used for transportation of goods fall outside the restriction "
        "entirely.",
        ["itc_blocked_17_5"],
        kind=STATUTE, certainty=FILED,
    ),
    Authority(
        "Orissa Concrete & Allied Industries v. Commissioner, 2023 SCC OnLine Ori",
        "The plant-and-machinery exception in Section 17(5)(d) takes a liberal "
        "construction.",
        ["itc_blocked_17_5"],
        forum="Orissa High Court",
    ),

    # -- ITC against 2A/2B and supplier default ---------------------------
    Authority(
        "Suncraft Energy Pvt. Ltd. v. Assistant Commissioner of State Tax, "
        "2023 SCC OnLine Cal 2805",
        "Input tax credit cannot be denied mechanically on a GSTR-2A/2B "
        "mismatch without inquiry into the supplier and without a show cause "
        "that discloses the case to be met.",
        ["itc_2a_2b_mismatch", "itc_supplier_default"],
        forum="Calcutta High Court",
        note="Persuasive outside West Bengal. Predates Section 16(2)(aa) on "
             "its facts — do not use it to bypass the post-amendment GSTR-2B "
             "condition.",
    ),
    Authority(
        "D.Y. Beathel Enterprises v. State Tax Officer, 2021 SCC OnLine Mad 21821",
        "Where credit is denied on a return mismatch, the officer must make an "
        "independent inquiry — including on the supplier side — before "
        "fastening liability on the recipient.",
        ["itc_2a_2b_mismatch", "itc_supplier_default"],
        forum="Madras High Court",
        note="Binding in Tamil Nadu. Concerns supplier default, not head "
             "misclassification — do not stretch it to a classification limb.",
    ),
    Authority(
        "LGW Industries Ltd. v. Union of India, 2022 SCC OnLine Cal 86",
        "Under Section 16(2)(c) the recipient is not constituted a tax "
        "collector for the government; a bona fide recipient who has satisfied "
        "the conditions within its own control cannot be visited with the "
        "supplier's default.",
        ["itc_supplier_default"],
        forum="Calcutta High Court",
    ),
    Authority(
        "Arise India Ltd. v. Commissioner of Trade & Taxes, 2018 (9) TMI 1461",
        "A bona fide purchaser cannot be penalised for the supplier's failure "
        "to deposit tax.",
        ["itc_supplier_default"],
        forum="Delhi High Court",
        note="VAT era; applicable by analogy only, and must be pleaded as such.",
    ),
    Authority(
        "Section 16(2)(aa), CGST Act, 2017 read with Rule 36(4) as substituted "
        "with effect from 01.01.2022",
        "For periods from 01.01.2022 the statutory comparator for eligibility "
        "is the invoice communicated in the STATIC GSTR-2B. The dynamic "
        "GSTR-2A is not the anchor, and a computation made against 2A — or "
        "against a mixed 2A/2B report — is liable to be recast.",
        ["itc_2a_2b_mismatch"],
        kind=STATUTE, certainty=FILED,
    ),
    Authority(
        "Section 50(3), CGST Act, 2017 read with Rule 88B",
        "Interest on wrongly availed input tax credit arises only where the "
        "credit has been availed AND utilised. Credit that sat unutilised in "
        "the electronic credit ledger attracts no interest.",
        ["itc_2a_2b_mismatch", "interest"],
        kind=STATUTE, certainty=FILED,
    ),
    Authority(
        "Section 155, CGST Act, 2017",
        "The burden of proving entitlement to input tax credit lies on the "
        "person claiming it — which is why the documentary record, not the "
        "argument, decides these limbs.",
        ["itc_2a_2b_mismatch", "itc_supplier_default", "itc_blocked_17_5"],
        kind=STATUTE, certainty=FILED,
    ),

    # -- ITC time limit ----------------------------------------------------
    Authority(
        "Sections 16(5) and 16(6), CGST Act, 2017 (inserted by the Finance "
        "(No. 2) Act, 2024)",
        "Retrospective relief from the Section 16(4) time bar for FY 2017-18 "
        "to FY 2020-21, and for registrations cancelled and subsequently "
        "restored. This is the primary answer to a legacy time-bar demand.",
        ["itc_time_limit"],
        kind=STATUTE,
    ),
    Authority(
        "Gobinda Construction v. Union of India, 2023 SCC OnLine Ori 2023",
        "The Section 16(4) time limit is procedural rather than substantive; a "
        "substantive right to credit is not defeated by a technicality.",
        ["itc_time_limit"],
        forum="Orissa High Court",
    ),

    # -- Credit notes and outward side ------------------------------------
    Authority(
        "Section 34 read with Section 34(2), CGST Act, 2017 and Rule 53",
        "A credit note reduces output tax liability where it is linked to a "
        "specific original invoice and declared not later than 30 November "
        "following the end of the financial year of the original supply, or "
        "the date of the annual return, whichever is earlier — and provided "
        "the recipient has reversed the corresponding credit.",
        ["credit_notes"],
        kind=STATUTE, certainty=FILED,
    ),
    Authority(
        "Section 15(3)(b), CGST Act, 2017",
        "Post-supply discount is excluded from value only where it was agreed "
        "at or before the time of supply, is linked to specific invoices, and "
        "the recipient has reversed the proportionate credit. Where no "
        "post-supply discount was issued at all, the provision does not arise "
        "and saying so disposes of the limb.",
        ["credit_notes"],
        kind=STATUTE, certainty=FILED,
    ),

    # -- E-invoicing and penalty ------------------------------------------
    Authority(
        "Notification No. 17/2022-Central Tax dated 01.08.2022",
        "Extends mandatory e-invoicing under Rule 48(4) to registered persons "
        "whose aggregate turnover exceeds Rs. 10 crore, with effect from "
        "01.10.2022.",
        ["einvoice"],
        kind=NOTIFICATION, certainty=FILED,
    ),
    Authority(
        "Notification No. 10/2023-Central Tax dated 10.05.2023",
        "Extends mandatory e-invoicing under Rule 48(4) to registered persons "
        "whose aggregate turnover exceeds Rs. 5 crore, with effect from "
        "01.08.2023. A taxpayer above Rs. 5 crore but below Rs. 10 crore is "
        "brought in on this date and not on 01.10.2022.",
        ["einvoice"],
        kind=NOTIFICATION, certainty=FILED,
        note="Decisive where the department has applied the wrong slab date. "
             "Must be paired with the IRP portal report proving compliance FROM "
             "that date — the notification alone does not carry the limb.",
    ),
    Authority(
        "Section 125, CGST Act, 2017",
        "The general penalty is predicated on an established contravention — "
        "'any person who contravenes'. It is not automatic, and in the absence "
        "of a proven contravention it has no application whatever.",
        ["einvoice", "penalty_general"],
        kind=STATUTE, certainty=FILED,
    ),
    Authority(
        "Section 126, CGST Act, 2017",
        "No penalty for minor breaches or procedural requirements, "
        "particularly where the breach is unintentional and there is no loss "
        "of revenue to the exchequer.",
        ["einvoice", "penalty_general", "minor_breach", "late_fee"],
        kind=STATUTE, certainty=FILED,
    ),

    # -- Limitation and suppression ---------------------------------------
    Authority(
        "Cosmic Dye Chemical v. Collector of Central Excise, 1995 (75) ELT 721",
        "Suppression must be wilful. Mere omission, without intent to evade, "
        "does not attract the extended period.",
        ["limitation", "suppression"],
        forum="Supreme Court",
    ),
    Authority(
        "Pushpam Pharmaceuticals Co. v. Collector of Central Excise, "
        "1995 (78) ELT 401",
        "A mere failure to declare is not suppression; a positive act of "
        "concealment is required before the extended period can be invoked.",
        ["limitation", "suppression"],
        forum="Supreme Court",
    ),
    Authority(
        "Continental Foundation Jt. Venture v. CCE, 2007 (216) ELT 177",
        "The department must establish suppression with evidence. It cannot be "
        "presumed from the existence of a difference.",
        ["limitation", "suppression"],
        forum="Supreme Court",
    ),
    Authority(
        "Section 75(7), CGST Act, 2017",
        "The demand confirmed can neither exceed the amount, nor rest on any "
        "ground other than those, specified in the show cause notice.",
        ["procedure", "limitation"],
        kind=STATUTE, certainty=FILED,
    ),

    # -- Natural justice and procedure ------------------------------------
    Authority(
        "Mohinder Singh Gill v. Chief Election Commissioner, AIR 1978 SC 851",
        "An order must stand on the reasons it states; those reasons cannot be "
        "supplemented afterwards by affidavit or argument.",
        ["natural_justice", "procedure"],
        forum="Supreme Court",
    ),
    Authority(
        "Section 75(4), CGST Act, 2017",
        "An opportunity of personal hearing must be granted where it is "
        "requested in writing, or where an adverse decision is contemplated.",
        ["natural_justice", "procedure"],
        kind=STATUTE, certainty=FILED,
    ),
    Authority(
        "Circular No. 128/47/2019-GST dated 23.12.2019",
        "A Document Identification Number is mandatory on departmental "
        "communications; a communication without a DIN is treated as invalid "
        "and deemed never to have been issued.",
        ["procedure", "natural_justice"],
        kind=CIRCULAR, forum="CBIC",
    ),
    Authority(
        "Section 61 read with Rule 99, CGST Act and Rules, 2017",
        "FORM GST ASMT-10 is an intimation of discrepancy on scrutiny, not a "
        "determination of tax. Where the explanation furnished in ASMT-11 is "
        "found acceptable the proper officer informs the registered person in "
        "ASMT-12 and no further action is taken; a demand requires a separate "
        "notice with the summary in DRC-01 under Rule 142(1).",
        ["procedure"],
        kind=STATUTE, certainty=FILED,
    ),
    Authority(
        "Sections 73(5) and 73(6), CGST Act, 2017",
        "Payment of tax with interest before issue of a show cause notice "
        "precludes a notice in respect of the amount so paid. This is the "
        "pre-notice route, and it is not Section 73(8), which governs payment "
        "AFTER a notice has issued.",
        ["payment", "penalty_general"],
        kind=STATUTE, certainty=FILED,
    ),

    # -- E-way bill --------------------------------------------------------
    Authority(
        "Section 129 read with Rule 138, CGST Act and Rules, 2017",
        "Detention and penalty require the ingredients of the section to be "
        "made out; a clerical defect in an e-way bill, absent any intent to "
        "evade, does not by itself sustain the penalty.",
        ["eway_bill"],
        kind=STATUTE,
    ),
]


def authorities_for_tags(tags: Iterable[str]) -> List[Dict[str, Any]]:
    """Authorities relevant to any of the given tags, filed ones first."""
    wanted = {t for t in tags if t}
    if not wanted:
        return []
    matched = [a for a in AUTHORITIES if wanted & set(a.tags)]
    matched.sort(key=lambda a: (a.certainty != FILED, a.kind != STATUTE))
    return [a.as_dict() for a in matched]


def authorities_for_defect(defect_type) -> List[Dict[str, Any]]:
    """
    Authorities to put in front of counsel arguing this defect type.

    The defect's own key is included as a tag so a catalogue entry need not
    restate it, and the authority tags stay readable.
    """
    tags = set(getattr(defect_type, "authority_tags", []) or [])
    tags.add(getattr(defect_type, "key", ""))
    return authorities_for_tags(tags)


def authorities_brief(authorities: List[Dict[str, Any]], limit: int = 8) -> str:
    """Render authorities as a prompt block for counsel."""
    if not authorities:
        return ""
    lines = [
        "AUTHORITIES HELD IN THE FIRM'S REFERENCE FOR THIS ISSUE.",
        "",
        "These are STARTING POINTS, not conclusions. Every one of them is put "
        "through live verification before it can reach the filing document, so "
        "cite one only where it genuinely decides the point on THESE facts, "
        "and say plainly where it does not fit. Adding an authority that does "
        "not bear on the issue is worse than citing none.",
        "",
    ]
    for entry in authorities[:limit]:
        lines.append(f"- {entry['citation']}"
                     + (f" [{entry['forum']}]" if entry.get("forum") else ""))
        lines.append(f"    {entry['proposition']}")
        if entry.get("note"):
            lines.append(f"    CAUTION: {entry['note']}")
    lines.append("")
    return "\n".join(lines)
