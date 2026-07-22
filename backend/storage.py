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
