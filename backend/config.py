"""Configuration for the LLM Council.

Every setting can be overridden with an environment variable (or a `.env`
file in the project root), so deployments never require code edits.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_list(name: str, default: list) -> list:
    """Parse a comma-separated environment variable into a list."""
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers.
# Override with e.g. COUNCIL_MODELS="openai/gpt-5.5,x-ai/grok-4.3"
COUNCIL_MODELS = _env_list("COUNCIL_MODELS", [
    "openai/gpt-5.5",
    "google/gemini-3.1-pro-preview",
    "anthropic/claude-opus-4.8",
    "x-ai/grok-4.3",
])

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = os.getenv("CHAIRMAN_MODEL", "google/gemini-3.1-pro-preview")

# Cheap/fast model used only for conversation titles
TITLE_MODEL = os.getenv("TITLE_MODEL", "google/gemini-2.5-flash")

# Reasoning effort requested from models that support it:
# "low" | "medium" | "high" | "none" (none = don't send the parameter)
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "medium")

# Per-request timeout (seconds) and retry budget for transient failures
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "180"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))

# How many prior user/assistant exchanges are sent as conversation context
HISTORY_MAX_TURNS = int(os.getenv("HISTORY_MAX_TURNS", "6"))

# Shared secret protecting the API. If unset/empty, auth is DISABLED —
# fine on localhost, required for any cloud deployment.
APP_ACCESS_TOKEN = os.getenv("APP_ACCESS_TOKEN", "")

# OpenRouter API endpoints
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Data directory for conversation storage (point at a persistent volume in prod)
DATA_DIR = os.getenv("DATA_DIR", "data/conversations")

# Server bind address. Backend runs on port 8001 by default (NOT 8000).
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))
