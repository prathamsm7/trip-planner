"""Input and output checks for Safar AI.

Input rules block jailbreaks, secret requests, and harmful requests before
the supervisor runs. Output sanitizing runs on every assistant message before
it is streamed or returned in a snapshot. It redacts key-shaped tokens and
replaces replies that leak internals. Travel wording such as "import duties"
is left intact.
"""

from __future__ import annotations

import re
from typing import Any, Literal

GuardrailAction = Literal["allow", "block"]

_BLOCK_RESPONSE = (
    "I'm Safar AI, your trip planning assistant. "
    "I can only help with planning trips, searching flights and hotels, "
    "and answering questions about your travel plans. "
    "How can I help you plan your next trip?"
)

_SAFE_FALLBACK = (
    "I can only share information about your trip. "
    "Is there anything about your travel plans I can help with?"
)

# Ask for *our* secrets or a dump of config. Bare words like "password" are
# normal in travel questions ("hotel wifi password") and must not match.
_SECRET_PATTERNS = [
    r"(?:your|the|our)\s+(?:api[_\s-]?key|secret[_\s-]?key|openai[_\s-]?key|serpapi[_\s-]?key|access[_\s-]?token)",
    r"(?:show|give|reveal|print|dump|leak|send)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:api[_\s-]?key|secret[_\s-]?key|\.env\b|env(?:ironment)?\s+variables?|access[_\s-]?token)",
    r"\b(?:openai|serpapi)[_\s-]?api[_\s-]?key\b",
    r"what(?:'s| is)\s+in\s+(?:your\s+)?\.env\b",
]

_PROMPT_DISCLOSURE_PATTERNS = [
    r"system\s+prompt",
    r"system\s+message",
    r"initial\s+prompt",
    r"original\s+instruction",
    r"internal\s+instruction",
    r"(?:give|show|reveal|print|repeat)\s+(?:me\s+)?(?:the\s+|your\s+)?system\s+prompt",
    r"(?:give|show|reveal|print|repeat)\s+(?:me\s+)?your\s+(?:system\s+)?(?:prompt|instructions)\b",
    r"what\s+(?:is|are)\s+your\s+(?:system\s+)?(?:prompt|instructions)\b",
]

_JAILBREAK_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous\s+|your\s+)?instructions",
    r"forget\s+(?:all\s+)?(?:previous\s+|your\s+)?(?:instructions|rules|prompt)",
    r"disregard\s+(?:all\s+)?(?:previous\s+|your\s+)?(?:instructions|rules)",
    r"bypass\s+(?:your\s+)?(?:safety|restrictions|rules|filters)",
    r"pretend\s+you\s+(?:are|have)\s+no\s+(?:rules|restrictions|limits)",
    r"act\s+as\s+(?:if\s+)?(?:you\s+)?(?:have\s+)?no\s+(?:rules|restrictions)",
    r"you\s+are\s+now\s+(?:free|unrestricted|unfiltered)",
    r"do\s+anything\s+now",
    r"\bdan\b.*\bmode\b",
    r"developer\s+mode",
    r"override\s+(?:your\s+)?(?:safety|restrictions|programming)",
    r"new\s+persona",
    r"roleplay\s+as\s+(?:a\s+)?(?:different|new|another)",
]

# Requests to *do* harm. Mentions of laws, visas, or customs stay allowed.
_UNSAFE_PATTERNS = [
    r"how\s+to\s+(?:hack|steal|break\s+into|exploit)",
    r"(?:write|generate|create)\s+(?:a\s+)?(?:malware|virus|exploit|phishing)",
    r"how\s+to\s+(?:buy|make|smuggle)\s+(?:illegal\s+)?(?:drugs|weapons)",
]

# Whole-reply replacement. Do not match ordinary travel words ("import duties").
_OUTPUT_LEAK_PATTERNS = [
    r"system\s*prompt",
    r"OPENAI_API_KEY",
    r"SERPAPI_API_KEY",
    r"MEM0_API_KEY",
    r"api_key\s*=",
    r"\bTravelState\b",
    r"\bfollow_up_questions\b",
    r"\buser_current_intent\b",
    r"\bguardrail_action\b",
    r"safar_api\.",
    r"def\s+\w+_node\(",
    r"\b(?:langgraph|langchain|structured_output)\b",
]

_SECRET_TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{12,}|sk-proj-[A-Za-z0-9_\-]{12,})\b"
)

def message_text(content: Any) -> str:
    """Flatten message content to text. List/multimodal content must not crash."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        return "\n".join(p for p in parts if p)
    return str(content)


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def rule_check(text: str) -> tuple[GuardrailAction, str] | None:
    """Block jailbreaks, secret requests, and harmful requests. None means allow."""
    if _matches_any(text, _SECRET_PATTERNS):
        return "block", "secret_request"
    if _matches_any(text, _PROMPT_DISCLOSURE_PATTERNS):
        return "block", "prompt_disclosure"
    if _matches_any(text, _JAILBREAK_PATTERNS):
        return "block", "jailbreak"
    if _matches_any(text, _UNSAFE_PATTERNS):
        return "block", "unsafe_content"
    return None


def evaluate_input(text: str) -> tuple[GuardrailAction, str]:
    """Apply input rules. Travel messages are allowed unless a rule matches."""
    text = message_text(text).strip()
    if not text:
        return "allow", "empty"

    ruled = rule_check(text)
    if ruled is not None:
        return ruled
    return "allow", "allow"


def refusal_message(action: GuardrailAction) -> str | None:
    if action == "block":
        return _BLOCK_RESPONSE
    return None


def sanitize_output(text: str) -> str:
    """Redact leaked secrets. Replace the reply only when internals are exposed."""
    if not text:
        return text
    cleaned = _SECRET_TOKEN.sub("[redacted]", text)
    if any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in _OUTPUT_LEAK_PATTERNS):
        return _SAFE_FALLBACK
    return cleaned
