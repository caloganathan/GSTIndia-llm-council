"""Tests for ranking parsing, aggregation, and history building."""

from backend.council import (
    build_history_messages,
    calculate_aggregate_rankings,
    format_history_snippet,
    parse_ranking_from_text,
)


class TestParseRanking:
    def test_strict_format(self):
        text = """Response A is decent. Response B is stronger.

FINAL RANKING:
1. Response B
2. Response A
3. Response C"""
        assert parse_ranking_from_text(text) == [
            "Response B", "Response A", "Response C"
        ]

    def test_duplicates_deduped(self):
        text = """FINAL RANKING:
1. Response B
2. Response B
3. Response A"""
        assert parse_ranking_from_text(text) == ["Response B", "Response A"]

    def test_invalid_labels_dropped(self):
        text = """FINAL RANKING:
1. Response D
2. Response A
3. Response B"""
        valid = ["Response A", "Response B", "Response C"]
        assert parse_ranking_from_text(text, valid) == ["Response A", "Response B"]

    def test_prose_mentions_after_header_ignored_when_numbered(self):
        text = """As I noted, Response C was weak.

FINAL RANKING:
1. Response A
2. Response B
3. Response C

Overall Response C had issues but Response A shined."""
        # Numbered-list matches take priority; trailing prose "Response C"/"A"
        # mentions are unnumbered and deduped away.
        assert parse_ranking_from_text(text) == [
            "Response A", "Response B", "Response C"
        ]

    def test_fallback_without_header(self):
        text = "Best is Response B, then Response A, finally Response C."
        assert parse_ranking_from_text(text) == [
            "Response B", "Response A", "Response C"
        ]

    def test_last_header_occurrence_wins(self):
        text = """I will provide my FINAL RANKING: below after analysis.
Response A is good. Response B is bad.

FINAL RANKING:
1. Response A
2. Response B"""
        assert parse_ranking_from_text(text) == ["Response A", "Response B"]

    def test_empty(self):
        assert parse_ranking_from_text("no labels here") == []


class TestAggregateRankings:
    LABELS = {
        "Response A": "model-a",
        "Response B": "model-b",
        "Response C": "model-c",
    }

    def test_normalized_scores(self):
        stage2 = [
            # Reviewer ranked B best, C worst (own response A excluded)
            {"parsed_ranking": ["Response B", "Response C"]},
            # Reviewer ranked A best, C worst (own response B excluded)
            {"parsed_ranking": ["Response A", "Response C"]},
        ]
        agg = calculate_aggregate_rankings(stage2, self.LABELS)
        by_model = {a["model"]: a for a in agg}
        assert by_model["model-a"]["score"] == 0.0
        assert by_model["model-b"]["score"] == 0.0
        assert by_model["model-c"]["score"] == 1.0
        assert by_model["model-c"]["rankings_count"] == 2
        # Sorted best (lowest score) first
        assert agg[-1]["model"] == "model-c"

    def test_empty_rankings_skipped(self):
        stage2 = [{"parsed_ranking": []}, {"parsed_ranking": ["Response A"]}]
        agg = calculate_aggregate_rankings(stage2, self.LABELS)
        assert len(agg) == 1
        assert agg[0]["model"] == "model-a"
        assert agg[0]["score"] == 0.5  # single-item ranking is uninformative

    def test_unknown_labels_ignored(self):
        stage2 = [{"parsed_ranking": ["Response Z", "Response A"]}]
        agg = calculate_aggregate_rankings(stage2, self.LABELS)
        assert [a["model"] for a in agg] == ["model-a"]


class TestHistory:
    MESSAGES = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "stage1": [], "stage2": [],
         "stage3": {"model": "m", "response": "first answer"}},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "stage1": [], "stage2": [],
         "stage3": {"model": "m", "response": "second answer"}},
    ]

    def test_builds_pairs(self):
        history = build_history_messages(self.MESSAGES)
        assert history == [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "second question"},
            {"role": "assistant", "content": "second answer"},
        ]

    def test_caps_turns(self):
        history = build_history_messages(self.MESSAGES, max_turns=1)
        assert history == [
            {"role": "user", "content": "second question"},
            {"role": "assistant", "content": "second answer"},
        ]

    def test_skips_failed_assistant_messages(self):
        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "stage3": {}},  # no response recorded
        ]
        assert build_history_messages(messages) == [
            {"role": "user", "content": "q"}
        ]

    def test_snippet_truncation(self):
        history = [{"role": "user", "content": "x" * 5000}]
        snippet = format_history_snippet(history, max_chars=100)
        assert "[...truncated]" in snippet
        assert len(snippet) < 200

    def test_snippet_empty(self):
        assert format_history_snippet([]) == ""
