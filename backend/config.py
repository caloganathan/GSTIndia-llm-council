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

# Root for all other persisted state: matters, user accounts, sessions.
#
# Derived from DATA_DIR by default so a single setting still works, but stated
# explicitly because deriving it was a data-loss bug: DATA_DIR="/app/data/"
# with a trailing slash resolved the parent to "/app", putting users.json
# OUTSIDE the mounted volume where it vanished on every redeploy. Set
# STATE_DIR directly to remove all doubt.
def _default_state_dir() -> str:
    normalised = DATA_DIR.rstrip("/\\")
    if not normalised:
        return "data"

    # Only step up when DATA_DIR is clearly the conversations subdirectory of a
    # state root ("<root>/conversations"). Anything else is treated as the root
    # itself, so DATA_DIR="/app/data/" keeps state inside /app/data rather than
    # writing it to /app, which on a container is outside the mounted volume.
    if os.path.basename(normalised).lower() == "conversations":
        parent = os.path.dirname(normalised)
        if parent and parent not in ("/", "."):
            return parent
    return normalised


STATE_DIR = os.getenv("STATE_DIR", "") or _default_state_dir()

# Server bind address. Backend runs on port 8001 by default (NOT 8000).
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))


# ---------------------------------------------------------------------------
# Compliance Panel (GST / IT adversarial panel)
# ---------------------------------------------------------------------------
# Two tiers. The tier is a RISK tier as much as a price tier:
#   free -> free/low-cost endpoints, client identifiers stripped by force
#   pro  -> frontier models, full facts, zero-data-retention routing
#
# Role keys: revenue, assessee, procedural, risk, chairman

PRO_ROLE_MODELS = {
    "revenue": os.getenv("PRO_MODEL_REVENUE", "x-ai/grok-4.3"),
    "assessee": os.getenv("PRO_MODEL_ASSESSEE", "anthropic/claude-opus-4.8"),
    "procedural": os.getenv("PRO_MODEL_PROCEDURAL", "openai/gpt-5.5"),
    "risk": os.getenv("PRO_MODEL_RISK", "google/gemini-3.1-pro-preview"),
    "chairman": os.getenv("PRO_MODEL_CHAIRMAN", "anthropic/claude-opus-4.8"),
}

FREE_ROLE_MODELS = {
    "revenue": os.getenv("FREE_MODEL_REVENUE", "deepseek/deepseek-r1:free"),
    "assessee": os.getenv("FREE_MODEL_ASSESSEE", "z-ai/glm-4.5-air:free"),
    "procedural": os.getenv("FREE_MODEL_PROCEDURAL", "qwen/qwen3-235b-a22b:free"),
    "risk": os.getenv("FREE_MODEL_RISK", "moonshotai/kimi-k2:free"),
    "chairman": os.getenv("FREE_MODEL_CHAIRMAN", "deepseek/deepseek-r1:free"),
}

# Model used to check citations against live sources (needs web search)
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "google/gemini-3.1-pro-preview")
FREE_VERIFIER_MODEL = os.getenv("FREE_VERIFIER_MODEL", "deepseek/deepseek-r1:free")

TIERS = {
    "free": {
        "key": "free",
        "label": "Free Council",
        "models": FREE_ROLE_MODELS,
        "verifier": FREE_VERIFIER_MODEL,
        # Enforced, not advisory: identifiers are stripped before any call.
        "anonymise": True,
        "allow_export": False,
        "watermark": "RESEARCH GRADE — NOT FOR FILING",
        "description": "Free endpoints. Client identifiers are stripped before "
                       "any request leaves this machine. Research and second "
                       "opinions only.",
    },
    "pro": {
        "key": "pro",
        "label": "Pro Council",
        "models": PRO_ROLE_MODELS,
        "verifier": VERIFIER_MODEL,
        "anonymise": False,
        "allow_export": True,
        "watermark": None,
        "description": "Frontier models with zero-data-retention routing. Full "
                       "facts, verified authorities, signing-ready pack.",
    },
}

DEFAULT_TIER = os.getenv("DEFAULT_PANEL_TIER", "pro")

# Ask OpenRouter to route only to providers that do not retain prompt data.
ENFORCE_ZDR = os.getenv("ENFORCE_ZDR", "true").lower() in ("1", "true", "yes")

# Standing note on every exported document.
#
# This is a working-paper control, in the register a manager uses when passing
# a file up for partner review — not a technology disclaimer. The document is
# the firm's work product; how it was prepared is internal, exactly as a
# junior's draft carries the partner's name and not the junior's. What the
# reviewer does need is a standing reminder of what to satisfy themselves on
# before the file is signed, and that is what this says.
EXPORT_REVIEW_NOTE = os.getenv(
    "EXPORT_REVIEW_NOTE",
    "Prepared for review. This draft is to be settled and signed by the "
    "engagement partner. Authorities shown as 'To be confirmed' or 'Not traced' "
    "in the Schedule of Authorities are to be independently verified against "
    "the reported text before this submission is filed or relied upon.",
)

# Firm identity printed on the export. Set these and the pack carries the
# firm's own name rather than a generic heading.
FIRM_NAME = os.getenv("FIRM_NAME", "")
FIRM_SUBTITLE = os.getenv("FIRM_SUBTITLE", "Chartered Accountants")

# Record the panel composition in an internal annexure. Off by default: the
# reply pack is a client deliverable, and the machinery behind it is not part
# of what the client or the department receives. The full record is always
# retained in the matter file regardless of this setting.
EXPORT_PROVENANCE = os.getenv("EXPORT_PROVENANCE", "false").lower() in (
    "1", "true", "yes"
)


def get_tier(name: str) -> dict:
    """Resolve a tier profile, falling back to the default."""
    return TIERS.get(name or DEFAULT_TIER, TIERS[DEFAULT_TIER])
