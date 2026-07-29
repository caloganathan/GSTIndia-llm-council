"""Reply deadlines — days remaining, urgency, and a calendar the firm can subscribe to.

WHY A WHOLE MODULE FOR SUBTRACTING TWO DATES
--------------------------------------------
Because the subtraction is not the point; the surfacing is. The single largest
source of avoidable loss in small-practice GST work is not bad drafting — it is
a notice nobody saw in time. The portal issues it, the email goes to an address
nobody watches, the reply window closes, and an ex-parte order follows under
s.73(9) for the full amount proposed. What was a reply becomes an appeal, with
a 10% pre-deposit and a limitation clock of its own.

The product already captured `due_date` and printed it on two documents.
Printing a date on a document that is read once is not a control. A control is
a number that is visible every time the user opens the application, sorted so
the worst one is at the top, and a calendar entry in the diary they actually
keep.

Three deliberate choices:

**Overdue matters sort ABOVE urgent ones and are never hidden.** A passed
deadline is not finished business — it is the matter that most needs a
decision this morning, because a condonation application or a s.161
rectification may still be open and both are time-barred in their turn.

**Urgency is banded, not continuous.** "14 days" and "11 days" call for the
same behaviour; "2 days" does not. Bands are what a reviewer acts on, and they
are what the UI can colour without inventing its own thresholds.

**The calendar is an export, not an integration.** An .ics file is opened by
Outlook, Google Calendar and Apple Calendar without an account, an API key or
a permission grant, and it works for a firm of three as well as a firm of
thirty. Anything richer belongs with the hosted offering, where there is a
server to hold the subscription.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

# Bands, in days remaining. Chosen against how the work actually moves: a reply
# needs documents from the client, and a client takes a week.
CRITICAL_DAYS = 3
URGENT_DAYS = 7

URGENCY_ORDER = {"overdue": 0, "critical": 1, "urgent": 2, "due": 3,
                 "none": 4}


def _as_date(value: Any) -> Optional[date]:
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


def days_remaining(due_date: Any, as_on: Any = None) -> Optional[int]:
    """
    Whole days from today to the deadline. Negative once it has passed.

    Zero means the deadline is today, which is a materially different state
    from one day left and is banded as critical accordingly.
    """
    due = _as_date(due_date)
    if due is None:
        return None
    today = _as_date(as_on) or date.today()
    return (due - today).days


def urgency(days: Optional[int]) -> str:
    """Band a day count. `none` means there is no deadline on file."""
    if days is None:
        return "none"
    if days < 0:
        return "overdue"
    if days <= CRITICAL_DAYS:
        return "critical"
    if days <= URGENT_DAYS:
        return "urgent"
    return "due"


def describe(days: Optional[int]) -> str:
    """
    The deadline in words, for a reviewer scanning a list.

    Written as the state of the matter rather than as a measurement: "overdue
    by 4 days" is a thing to act on, "-4" is not.
    """
    if days is None:
        return "No reply date on file"
    if days < 0:
        return f"OVERDUE by {abs(days)} day{'s' if abs(days) != 1 else ''}"
    if days == 0:
        return "Due TODAY"
    if days == 1:
        return "Due tomorrow"
    return f"{days} days remaining"


def annotate(matter: Dict[str, Any], as_on: Any = None) -> Dict[str, Any]:
    """Add the deadline fields to a matter summary, in place."""
    days = days_remaining(matter.get("due_date"), as_on)
    matter["days_remaining"] = days
    matter["urgency"] = urgency(days)
    matter["deadline_label"] = describe(days)
    return matter


def sort_key(matter: Dict[str, Any]):
    """
    Worst first: overdue, then critical, then urgent, then the rest.

    Within a band the nearer deadline leads. Matters with no deadline sort
    last — they are not urgent, but they are not hidden either, because a
    matter whose reply date was never captured is its own kind of problem.
    """
    band = URGENCY_ORDER.get(matter.get("urgency", "none"), 4)
    days = matter.get("days_remaining")
    return (band, days if days is not None else 10**6)


def summarise(matters: Iterable[Dict[str, Any]],
              as_on: Any = None) -> Dict[str, Any]:
    """
    The deadline position across the whole book of work.

    This is what goes at the top of the dashboard. `attention` is the count a
    partner is answering when they ask "what has to move today".
    """
    annotated = [annotate(dict(m), as_on) for m in matters]
    # A matter that has been filed is not chasing a deadline. Only live work
    # counts towards the numbers that drive behaviour.
    live = [m for m in annotated if m.get("status") != "filed"]

    counts = {"overdue": 0, "critical": 0, "urgent": 0, "due": 0, "none": 0}
    for matter in live:
        counts[matter["urgency"]] = counts.get(matter["urgency"], 0) + 1

    upcoming = sorted(
        [m for m in live if m["urgency"] in ("overdue", "critical", "urgent")],
        key=sort_key,
    )

    return {
        "counts": counts,
        "attention": counts["overdue"] + counts["critical"] + counts["urgent"],
        "no_deadline": counts["none"],
        "upcoming": upcoming[:10],
    }


# ---------------------------------------------------------------------------
# Calendar export
# ---------------------------------------------------------------------------
# RFC 5545 by hand. An iCalendar library would be one more dependency for a
# file format whose entire relevant surface is twelve lines, and the escaping
# rules below are the only part with any subtlety.


def _escape(text: str) -> str:
    """Escape per RFC 5545 §3.3.11. Backslash first or it doubles the rest."""
    return (str(text or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n"))


def _fold(line: str) -> str:
    """
    Fold to 75 octets, continuation lines beginning with a space (§3.1).

    Unfolded long lines are accepted by most clients and rejected by some;
    Outlook is in the second group often enough to matter.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts, current = [], ""
    for char in line:
        candidate = current + char
        limit = 75 if not parts else 74      # continuations carry a leading space
        if len(candidate.encode("utf-8")) > limit:
            parts.append(current)
            current = char
        else:
            current = candidate
    if current:
        parts.append(current)
    return "\r\n ".join(parts)


def build_ics(matters: Iterable[Dict[str, Any]],
              product: str = "Compliance Panel") -> str:
    """
    An iCalendar feed of every reply deadline on file.

    All-day events with an alarm two days out. Two days rather than one
    because a reply needs the client's documents, and a reminder that arrives
    the day before is a reminder that arrives too late to ask for anything.

    Client names go into the calendar — this file is the firm's own diary, and
    a calendar entry reading "Reply due — matter a3f2c1" is one nobody acts
    on. It is never sent anywhere; it downloads to the machine that asked.
    """
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{_escape(product)}//Reply deadlines//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(product)} — reply deadlines",
    ]

    for matter in matters:
        due = _as_date(matter.get("due_date"))
        if due is None:
            continue

        client = matter.get("client_name") or "Client not named"
        notice = matter.get("notice_type") or "Notice"
        period = matter.get("tax_period") or ""

        summary = f"{notice} reply due — {client}"
        description_parts = [
            f"Reply to {notice} is due on {due.strftime('%d.%m.%Y')}.",
            f"Client: {client}",
        ]
        if period:
            description_parts.append(f"Period: {period}")
        if matter.get("state"):
            description_parts.append(f"State: {matter['state']}")
        if matter.get("amount_disputed"):
            description_parts.append(
                f"Amount in dispute: Rs. {matter['amount_disputed']:,.2f}")
        description_parts.append(f"Matter reference: {matter.get('id', '')}")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{_escape(matter.get('id', ''))}@compliance-panel",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}",
            # DTEND is exclusive for all-day events, so a one-day event ends
            # the following day. Omitting this makes the entry vanish in some
            # clients and span two days in others.
            f"DTEND;VALUE=DATE:{(due + timedelta(days=1)).strftime('%Y%m%d')}",
            _fold(f"SUMMARY:{_escape(summary)}"),
            _fold(f"DESCRIPTION:{_escape(chr(10).join(description_parts))}"),
            "TRANSP:TRANSPARENT",
            "BEGIN:VALARM",
            "TRIGGER:-P2D",
            "ACTION:DISPLAY",
            _fold(f"DESCRIPTION:{_escape(summary)}"),
            "END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
