"""
Persistence for conversations and matters.

Both record types are JSON documents in a directory, and both are written the
same way: to a temporary file in the destination directory, then moved into
place with `os.replace`. That move is atomic on POSIX and on Windows, so a
crash or a full disk mid-write leaves the previous version intact. There is no
half-written state a reader can observe.

This matters more for matters than for conversations. A matter record is the
working paper — the notice facts, the deliberation, the determination and the
verification trail — and a firm relying on it at peer review needs it to be
either the old version or the new one, never a truncated hybrid.

Corrupt files are skipped in listings and return None on read. A single bad
document must never take down the index.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import config

DEFAULT_TITLE = "New Conversation"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Document primitives
#
# Conversations and matters differ only in which directory they live in and
# what shape they carry. Everything about getting them onto and off disk is
# shared, and is written once here.
# ---------------------------------------------------------------------------


def _write_document(directory: str, name: str, document: Dict[str, Any]) -> None:
    """Write one JSON document atomically, creating the directory if needed."""
    Path(directory).mkdir(parents=True, exist_ok=True)
    handle, staging_path = tempfile.mkstemp(
        dir=directory, prefix=".tmp-", suffix=".json"
    )
    try:
        with os.fdopen(handle, "w") as staged:
            json.dump(document, staged, indent=2)
        os.replace(staging_path, os.path.join(directory, f"{name}.json"))
    except BaseException:
        # Never leave a stray .tmp- file behind, whatever went wrong.
        try:
            os.unlink(staging_path)
        except OSError:
            pass
        raise


def _read_document(directory: str, name: str,
                   label: str) -> Optional[Dict[str, Any]]:
    """Load one JSON document, or None if it is absent or unreadable."""
    path = os.path.join(directory, f"{name}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as stored:
            return json.load(stored)
    except (json.JSONDecodeError, OSError) as problem:
        print(f"Could not read {label} {name}: {problem}")
        return None


def _remove_document(directory: str, name: str) -> bool:
    """Delete one document. True if it was there to delete."""
    path = os.path.join(directory, f"{name}.json")
    if not os.path.exists(path):
        return False
    os.unlink(path)
    return True


def _scan_documents(
    directory: str,
    summarise: Callable[[Dict[str, Any]], Dict[str, Any]],
    label: str,
) -> List[Dict[str, Any]]:
    """
    Read every document in a directory and reduce each to a summary.

    Anything that will not parse, or that is missing a field the summary needs,
    is reported and skipped — one damaged file must not empty the index.
    """
    Path(directory).mkdir(parents=True, exist_ok=True)

    summaries: List[Dict[str, Any]] = []
    for filename in os.listdir(directory):
        if not filename.endswith(".json") or filename.startswith("."):
            continue
        try:
            with open(os.path.join(directory, filename), "r") as stored:
                summaries.append(summarise(json.load(stored)))
        except (json.JSONDecodeError, KeyError, OSError, TypeError) as problem:
            print(f"Skipping unreadable {label} file {filename}: {problem}")

    summaries.sort(key=lambda entry: entry["created_at"], reverse=True)
    return summaries


# ---------------------------------------------------------------------------
# Conversations — the general council
# ---------------------------------------------------------------------------
#
# config.DATA_DIR is read at call time rather than bound at import, so tests
# can redirect storage with a monkeypatch. Keep it that way.


def ensure_data_dir() -> None:
    Path(config.DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    return os.path.join(config.DATA_DIR, f"{conversation_id}.json")


def save_conversation(conversation: Dict[str, Any]) -> None:
    _write_document(config.DATA_DIR, conversation["id"], conversation)


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    return _read_document(config.DATA_DIR, conversation_id, "conversation")


def delete_conversation(conversation_id: str) -> bool:
    return _remove_document(config.DATA_DIR, conversation_id)


def create_conversation(conversation_id: str) -> Dict[str, Any]:
    conversation = {
        "id": conversation_id,
        "created_at": _now(),
        "title": DEFAULT_TITLE,
        "messages": [],
    }
    save_conversation(conversation)
    return conversation


def list_conversations() -> List[Dict[str, Any]]:
    """Conversation summaries for the sidebar, newest first."""
    def summarise(document: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": document["id"],
            "created_at": document["created_at"],
            "title": document.get("title", DEFAULT_TITLE),
            "message_count": len(document["messages"]),
        }

    return _scan_documents(config.DATA_DIR, summarise, "conversation")


def _append_message(conversation_id: str, message: Dict[str, Any]) -> None:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    conversation["messages"].append(message)
    save_conversation(conversation)


def add_user_message(conversation_id: str, content: str) -> None:
    _append_message(conversation_id, {"role": "user", "content": content})


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record one full exchange.

    The metadata — label mapping, aggregate ordering, per-model failures and
    cost — is persisted alongside the stages, so a reloaded conversation
    renders exactly as it did live rather than losing its provenance.
    """
    _append_message(conversation_id, {
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "metadata": metadata or {},
    })


def update_conversation_title(conversation_id: str, title: str) -> None:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    conversation["title"] = title
    save_conversation(conversation)


# ---------------------------------------------------------------------------
# Matters — the compliance panel
#
# A matter is the unit of work for the panel: the notice facts, the full
# deliberation, the determination, and the verification result. Persisting the
# whole deliberation is not an implementation detail — that record IS the
# working paper the firm relies on at peer review.
# ---------------------------------------------------------------------------


def _matters_dir() -> str:
    return os.path.join(config.STATE_DIR, "matters")


def _matter_path(matter_id: str) -> str:
    return os.path.join(_matters_dir(), f"{matter_id}.json")


def save_matter(matter: Dict[str, Any]) -> None:
    _write_document(_matters_dir(), matter["id"], matter)


def get_matter(matter_id: str) -> Optional[Dict[str, Any]]:
    return _read_document(_matters_dir(), matter_id, "matter")


def delete_matter(matter_id: str) -> bool:
    return _remove_document(_matters_dir(), matter_id)


def create_matter(matter_id: str, intake: Dict[str, Any], domain: str,
                  tier: str, created_by: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create a matter record from the intake form."""
    opened_at = _now()
    matter = {
        "id": matter_id,
        "created_at": opened_at,
        "updated_at": opened_at,
        "domain": domain,
        "tier": tier,
        "status": "draft",
        "intake": intake,
        "result": None,
        "metadata": {},
        "created_by": {
            "id": (created_by or {}).get("id"),
            "name": (created_by or {}).get("name"),
            "email": (created_by or {}).get("email"),
        } if created_by else None,
    }
    save_matter(matter)
    return matter


def complete_matter(matter_id: str, result: Dict[str, Any],
                    metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Attach the panel output to a matter and mark it complete."""
    matter = get_matter(matter_id)
    if matter is None:
        return None
    matter["result"] = result
    matter["metadata"] = metadata
    matter["status"] = "complete"
    matter["updated_at"] = _now()
    save_matter(matter)
    return matter


def list_matters() -> List[Dict[str, Any]]:
    """Matter summaries for the dashboard, newest first."""
    def summarise(document: Dict[str, Any]) -> Dict[str, Any]:
        intake = document.get("intake", {})
        outcome = document.get("result") or {}
        determination = outcome.get("determination") or {}
        verification = outcome.get("verification") or {}
        limbs = intake.get("defects") or []
        # Cost scales with the limbs that convened counsel, not with the limb
        # count, so the estimator needs both to learn from this matter.
        panel_limbs = [d for d in limbs
                       if (d.get("posture") or "undecided")
                       in ("contested", "partial", "undecided")]
        return {
            "id": document["id"],
            "defect_count": len(limbs),
            "panel_defect_count": len(panel_limbs),
            "created_at": document["created_at"],
            "updated_at": document.get("updated_at", document["created_at"]),
            "domain": document.get("domain", "gst"),
            "tier": document.get("tier"),
            "status": document.get("status", "draft"),
            "client_name": intake.get("client_name", ""),
            "notice_type": intake.get("notice_type", ""),
            "state": intake.get("state", ""),
            "tax_period": intake.get("tax_period", ""),
            "amount_disputed": intake.get("amount_disputed"),
            "due_date": intake.get("due_date"),
            "confidence": determination.get("confidence"),
            "risk_flag_count": len(determination.get("risk_flags") or []),
            "verification_summary": verification.get("summary"),
            "usage": (document.get("metadata") or {}).get("usage"),
            "created_by": document.get("created_by"),
        }

    return _scan_documents(_matters_dir(), summarise, "matter")
