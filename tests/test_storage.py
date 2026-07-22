"""Tests for conversation storage."""

import json
import os

import pytest

from backend import config, storage


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_create_and_get():
    conv = storage.create_conversation("abc")
    assert conv["id"] == "abc"
    loaded = storage.get_conversation("abc")
    assert loaded["title"] == "New Conversation"
    assert loaded["messages"] == []


def test_add_messages_and_metadata_persisted():
    storage.create_conversation("abc")
    storage.add_user_message("abc", "hello")
    storage.add_assistant_message(
        "abc",
        stage1=[{"model": "m1", "response": "r1"}],
        stage2=[],
        stage3={"model": "m1", "response": "final"},
        metadata={"usage": {"total_cost": 0.5}},
    )
    loaded = storage.get_conversation("abc")
    assert len(loaded["messages"]) == 2
    assistant = loaded["messages"][1]
    assert assistant["metadata"]["usage"]["total_cost"] == 0.5


def test_delete():
    storage.create_conversation("abc")
    assert storage.delete_conversation("abc") is True
    assert storage.get_conversation("abc") is None
    assert storage.delete_conversation("abc") is False


def test_corrupt_file_skipped_in_listing(temp_data_dir):
    storage.create_conversation("good")
    (temp_data_dir / "bad.json").write_text("{not json")
    listing = storage.list_conversations()
    assert [c["id"] for c in listing] == ["good"]


def test_corrupt_file_returns_none():
    path = storage.get_conversation_path("bad")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("{not json")
    assert storage.get_conversation("bad") is None


def test_no_temp_files_left_behind(temp_data_dir):
    storage.create_conversation("abc")
    leftovers = [f for f in os.listdir(temp_data_dir) if f.startswith(".tmp-")]
    assert leftovers == []


def test_listing_sorted_newest_first(temp_data_dir):
    for cid, ts in [("one", "2026-01-01T00:00:00"), ("two", "2026-06-01T00:00:00")]:
        storage.save_conversation({
            "id": cid, "created_at": ts, "title": cid, "messages": []
        })
    listing = storage.list_conversations()
    assert [c["id"] for c in listing] == ["two", "one"]
