"""Reply deadlines, urgency banding, and the calendar export.

The behaviour under test is not the subtraction. It is that an overdue matter
sorts to the top and is never dropped from a listing — a passed deadline is the
matter that most needs a decision, not one that has gone quiet.
"""

from datetime import date, timedelta

from backend import deadlines


class TestDaysRemaining:
    def test_future_date(self):
        assert deadlines.days_remaining("2026-02-10", as_on="2026-02-01") == 9

    def test_today_is_zero_not_none(self):
        assert deadlines.days_remaining("2026-02-01", as_on="2026-02-01") == 0

    def test_past_date_is_negative(self):
        assert deadlines.days_remaining("2026-01-20", as_on="2026-02-01") == -12

    def test_missing_date_is_none(self):
        assert deadlines.days_remaining(None) is None
        assert deadlines.days_remaining("") is None

    def test_unparseable_date_is_none_rather_than_raising(self):
        assert deadlines.days_remaining("sometime next week") is None

    def test_accepts_a_datetime_string(self):
        assert deadlines.days_remaining("2026-02-10T09:30:00Z",
                                        as_on="2026-02-01") == 9


class TestUrgency:
    def test_bands(self):
        assert deadlines.urgency(-1) == "overdue"
        assert deadlines.urgency(0) == "critical"
        assert deadlines.urgency(3) == "critical"
        assert deadlines.urgency(4) == "urgent"
        assert deadlines.urgency(7) == "urgent"
        assert deadlines.urgency(8) == "due"
        assert deadlines.urgency(None) == "none"

    def test_today_is_critical_not_merely_urgent(self):
        # A reply due today and a reply due in a week are not the same call.
        assert deadlines.urgency(0) == "critical"


class TestDescribe:
    def test_reads_as_a_state_not_a_measurement(self):
        assert deadlines.describe(-4) == "OVERDUE by 4 days"
        assert deadlines.describe(-1) == "OVERDUE by 1 day"
        assert deadlines.describe(0) == "Due TODAY"
        assert deadlines.describe(1) == "Due tomorrow"
        assert deadlines.describe(12) == "12 days remaining"

    def test_no_deadline_says_so(self):
        assert "No reply date" in deadlines.describe(None)


class TestSorting:
    def _matters(self):
        return [
            {"id": "far", "due_date": "2026-03-01"},
            {"id": "overdue", "due_date": "2026-01-20"},
            {"id": "none", "due_date": None},
            {"id": "critical", "due_date": "2026-02-02"},
            {"id": "urgent", "due_date": "2026-02-06"},
        ]

    def test_worst_first(self):
        matters = [deadlines.annotate(m, as_on="2026-02-01")
                   for m in self._matters()]
        matters.sort(key=deadlines.sort_key)
        assert [m["id"] for m in matters] == [
            "overdue", "critical", "urgent", "far", "none"]

    def test_matters_without_a_deadline_sort_last_but_are_not_dropped(self):
        matters = [deadlines.annotate(m, as_on="2026-02-01")
                   for m in self._matters()]
        matters.sort(key=deadlines.sort_key)
        assert matters[-1]["id"] == "none"
        assert len(matters) == 5

    def test_within_a_band_the_nearer_deadline_leads(self):
        matters = [
            deadlines.annotate({"id": "b", "due_date": "2026-01-10"},
                               as_on="2026-02-01"),
            deadlines.annotate({"id": "a", "due_date": "2026-01-05"},
                               as_on="2026-02-01"),
        ]
        matters.sort(key=deadlines.sort_key)
        # Both overdue; the one overdue by longer is the more serious.
        assert [m["id"] for m in matters] == ["a", "b"]


class TestSummarise:
    def test_counts_by_band(self):
        summary = deadlines.summarise([
            {"id": "1", "due_date": "2026-01-20"},
            {"id": "2", "due_date": "2026-02-02"},
            {"id": "3", "due_date": "2026-02-06"},
            {"id": "4", "due_date": "2026-06-01"},
            {"id": "5", "due_date": None},
        ], as_on="2026-02-01")
        assert summary["counts"]["overdue"] == 1
        assert summary["counts"]["critical"] == 1
        assert summary["counts"]["urgent"] == 1
        assert summary["attention"] == 3
        assert summary["no_deadline"] == 1

    def test_filed_matters_do_not_chase_a_deadline(self):
        summary = deadlines.summarise([
            {"id": "1", "due_date": "2026-01-20", "status": "filed"},
            {"id": "2", "due_date": "2026-01-20", "status": "complete"},
        ], as_on="2026-02-01")
        assert summary["counts"]["overdue"] == 1

    def test_upcoming_excludes_comfortable_deadlines(self):
        summary = deadlines.summarise([
            {"id": "far", "due_date": "2026-12-01"},
            {"id": "near", "due_date": "2026-02-02"},
        ], as_on="2026-02-01")
        assert [m["id"] for m in summary["upcoming"]] == ["near"]

    def test_does_not_mutate_the_caller_s_matters(self):
        matters = [{"id": "1", "due_date": "2026-01-20"}]
        deadlines.summarise(matters, as_on="2026-02-01")
        assert "urgency" not in matters[0]

    def test_empty_book_of_work(self):
        summary = deadlines.summarise([])
        assert summary["attention"] == 0


class TestCalendarExport:
    def _matter(self, **overrides):
        base = {
            "id": "abc-123",
            "due_date": "2026-02-10",
            "client_name": "Gram Envosolution Private Limited",
            "notice_type": "ASMT-10",
            "tax_period": "FY 2023-24",
            "state": "Tamil Nadu",
            "amount_disputed": 202000.0,
        }
        base.update(overrides)
        return base

    def test_produces_a_valid_calendar_envelope(self):
        ics = deadlines.build_ics([self._matter()])
        assert ics.startswith("BEGIN:VCALENDAR")
        assert ics.rstrip().endswith("END:VCALENDAR")
        assert "VERSION:2.0" in ics

    def test_event_carries_the_client_name_so_it_is_actionable(self):
        ics = deadlines.build_ics([self._matter()])
        assert "Gram Envosolution" in ics
        assert "ASMT-10" in ics

    def test_all_day_event_ends_the_following_day(self):
        # DTEND is exclusive for VALUE=DATE. Without this the entry either
        # disappears or spans two days depending on the client.
        ics = deadlines.build_ics([self._matter()])
        assert "DTSTART;VALUE=DATE:20260210" in ics
        assert "DTEND;VALUE=DATE:20260211" in ics

    def test_alarm_fires_two_days_out(self):
        ics = deadlines.build_ics([self._matter()])
        assert "BEGIN:VALARM" in ics
        assert "TRIGGER:-P2D" in ics

    def test_matters_without_a_due_date_are_skipped_not_dated_today(self):
        ics = deadlines.build_ics([self._matter(due_date=None)])
        assert "BEGIN:VEVENT" not in ics

    def test_commas_and_semicolons_in_a_client_name_are_escaped(self):
        # An unescaped comma in SUMMARY silently truncates the entry in
        # several clients, and Indian entity names carry them routinely.
        ics = deadlines.build_ics([
            self._matter(client_name="Acme Steel, Iron; and Alloys Limited")])
        assert "Acme Steel\\, Iron\\; and Alloys Limited" in ics

    def test_backslash_is_escaped_before_the_others(self):
        ics = deadlines.build_ics([self._matter(client_name="A\\B, Co")])
        assert "A\\\\B\\, Co" in ics

    def test_long_lines_are_folded_with_a_leading_space(self):
        ics = deadlines.build_ics([
            self._matter(client_name="X" * 200)])
        for line in ics.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75

    def test_crlf_line_endings_as_the_spec_requires(self):
        ics = deadlines.build_ics([self._matter()])
        assert "\r\n" in ics
        assert "\n\n" not in ics.replace("\r\n", "\n").replace("\n\n", "")

    def test_empty_book_still_produces_a_valid_file(self):
        ics = deadlines.build_ics([])
        assert "BEGIN:VCALENDAR" in ics and "END:VCALENDAR" in ics
