"""JSON-based storage for conversations, with atomic writes."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(config.DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation."""
    return os.path.join(config.DATA_DIR, f"{conversation_id}.json")


def create_conversation(conversation_id: str) -> Dict[str, Any]:
    """Create a new conversation and persist it."""
    conversation = {
        "id": conversation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": "New Conversation",
        "messages": []
    }
    save_conversation(conversation)
    return conversation


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Load a conversation from storage, or None if missing/corrupt."""
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return None

    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading conversation {conversation_id}: {e}")
        return None


def save_conversation(conversation: Dict[str, Any]):
    """Save a conversation atomically (temp file + rename)."""
    ensure_data_dir()

    path = get_conversation_path(conversation['id'])
    fd, tmp_path = tempfile.mkstemp(
        dir=config.DATA_DIR, prefix=".tmp-", suffix=".json"
    )
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(conversation, f, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation. Returns True if it existed."""
    path = get_conversation_path(conversation_id)
    if not os.path.exists(path):
        return False
    os.unlink(path)
    return True


def list_conversations() -> List[Dict[str, Any]]:
    """List all conversations (metadata only), newest first."""
    ensure_data_dir()

    conversations = []
    for filename in os.listdir(config.DATA_DIR):
        if not filename.endswith('.json') or filename.startswith('.'):
            continue
        path = os.path.join(config.DATA_DIR, filename)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            conversations.append({
                "id": data["id"],
                "created_at": data["created_at"],
                "title": data.get("title", "New Conversation"),
                "message_count": len(data["messages"])
            })
        except (json.JSONDecodeError, KeyError, OSError) as e:
            # Skip corrupt files rather than breaking the whole listing
            print(f"Skipping unreadable conversation file {filename}: {e}")

    conversations.sort(key=lambda x: x["created_at"], reverse=True)
    return conversations


def add_user_message(conversation_id: str, content: str):
    """Add a user message to a conversation."""
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "user",
        "content": content
    })

    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
):
    """Add an assistant message with all stages (and metadata) to a conversation."""
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "metadata": metadata or {},
    })

    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str):
    """Update the title of a conversation."""
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["title"] = title
    save_conversation(conversation)


# ---------------------------------------------------------------------------
# Compliance Panel matters
#
# A matter is the unit of work for the panel: the notice facts, the full
# deliberation, the determination, and the verification result. Persisting the
# whole deliberation is not an implementation detail — that record IS the
# working paper the firm relies on at peer review.
# ---------------------------------------------------------------------------


def _matters_dir() -> str:
    return os.path.join(os.path.dirname(config.DATA_DIR.rstrip("/")), "matters")


def _matter_path(matter_id: str) -> str:
    return os.path.join(_matters_dir(), f"{matter_id}.json")


def save_matter(matter: Dict[str, Any]):
    """Persist a matter atomically."""
    directory = _matters_dir()
    Path(directory).mkdir(parents=True, exist_ok=True)

    path = _matter_path(matter["id"])
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(matter, f, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def create_matter(matter_id: str, intake: Dict[str, Any], domain: str,
                  tier: str, created_by: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create a matter record from the intake form."""
    matter = {
        "id": matter_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
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


def get_matter(matter_id: str) -> Optional[Dict[str, Any]]:
    path = _matter_path(matter_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading matter {matter_id}: {e}")
        return None


def complete_matter(matter_id: str, result: Dict[str, Any],
                    metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Attach the panel output to a matter and mark it complete."""
    matter = get_matter(matter_id)
    if matter is None:
        return None
    matter["result"] = result
    matter["metadata"] = metadata
    matter["status"] = "complete"
    matter["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_matter(matter)
    return matter


def delete_matter(matter_id: str) -> bool:
    path = _matter_path(matter_id)
    if not os.path.exists(path):
        return False
    os.unlink(path)
    return True


def list_matters() -> List[Dict[str, Any]]:
    """Matter summaries for the dashboard, newest first."""
    directory = _matters_dir()
    Path(directory).mkdir(parents=True, exist_ok=True)

    matters = []
    for filename in os.listdir(directory):
        if not filename.endswith('.json') or filename.startswith('.'):
            continue
        try:
            with open(os.path.join(directory, filename), 'r') as f:
                data = json.load(f)
            intake = data.get("intake", {})
            determination = (data.get("result") or {}).get("determination") or {}
            verification = (data.get("result") or {}).get("verification") or {}
            matters.append({
                "id": data["id"],
                "created_at": data["created_at"],
                "updated_at": data.get("updated_at", data["created_at"]),
                "domain": data.get("domain", "gst"),
                "tier": data.get("tier"),
                "status": data.get("status", "draft"),
                "client_name": intake.get("client_name", ""),
                "notice_type": intake.get("notice_type", ""),
                "state": intake.get("state", ""),
                "tax_period": intake.get("tax_period", ""),
                "amount_disputed": intake.get("amount_disputed"),
                "due_date": intake.get("due_date"),
                "confidence": determination.get("confidence"),
                "risk_flag_count": len(determination.get("risk_flags") or []),
                "verification_summary": verification.get("summary"),
                "usage": (data.get("metadata") or {}).get("usage"),
                "created_by": data.get("created_by"),
            })
        except (json.JSONDecodeError, KeyError, OSError) as e:
            print(f"Skipping unreadable matter file {filename}: {e}")

    matters.sort(key=lambda m: m["created_at"], reverse=True)
    return matters
