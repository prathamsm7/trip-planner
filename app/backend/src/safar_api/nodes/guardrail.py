"""Input & output guardrails for Safar AI.

Input guardrail runs BEFORE intent classification and catches:
  - Prompt injection / jailbreak attempts
  - API key / secret exfiltration requests
  - System prompt disclosure requests
  - Unsafe / harmful content

Output guardrail runs AFTER LLM responses and sanitizes:
  - Leaked system prompts or internal state
  - Accidental exposure of keys, env vars, or technical internals
"""

from __future__ import annotations

import re
from typing import Literal

from langchain_core.messages import AIMessage

from safar_api.models.state import TravelState

GuardrailAction = Literal["allow", "block", "redirect"]

_BLOCK_RESPONSE = (
    "I'm Safar AI, your trip planning assistant. "
    "I can only help with planning trips, searching flights and hotels, "
    "and answering questions about your travel plans. "
    "How can I help you plan your next trip?"
)

_REDIRECT_RESPONSE = (
    "That's an interesting question, but I'm designed specifically for trip planning. "
    "I can help you plan a trip, find flights, search hotels, check weather, "
    "or answer questions about your travel plans. What would you like to do?"
)

# ── Input patterns ──────────────────────────────────────────────────

_SECRET_PATTERNS = [
    r"api[_\s-]?key",
    r"secret[_\s-]?key",
    r"password",
    r"credentials",
    r"env[_\s-]?var",
    r"environment\s+variable",
    r"\.env\b",
    r"openai[_\s-]?key",
    r"serpapi[_\s-]?key",
    r"access[_\s-]?token",
]

_PROMPT_DISCLOSURE_PATTERNS = [
    r"system\s+prompt",
    r"system\s+message",
    r"initial\s+prompt",
    r"original\s+instruction",
    r"internal\s+instruction",
    r"give\s+me\s+(?:the\s+)?(?:your\s+)?prompt",
    r"show\s+me\s+(?:the\s+)?(?:your\s+)?prompt",
    r"what\s+(?:is|are)\s+your\s+(?:system\s+)?instructions",
    r"reveal\s+(?:your\s+)?(?:system\s+)?prompt",
    r"print\s+(?:your\s+)?(?:system\s+)?prompt",
    r"repeat\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions)",
]

_JAILBREAK_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous\s+)?(?:your\s+)?instructions",
    r"forget\s+(?:all\s+)?(?:previous\s+)?(?:your\s+)?(?:instructions|rules|prompt)",
    r"disregard\s+(?:all\s+)?(?:previous\s+)?(?:your\s+)?(?:instructions|rules)",
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

_UNSAFE_PATTERNS = [
    r"how\s+to\s+(?:hack|steal|break\s+into|exploit)",
    r"generate\s+(?:malware|virus|exploit|phishing)",
    r"illegal\s+(?:activity|substance|drug)",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in patterns)


def check_input(text: str) -> tuple[GuardrailAction, str]:
    """Classify user input and return (action, reason)."""
    if _matches_any(text, _SECRET_PATTERNS):
        return "block", "secret_request"
    if _matches_any(text, _PROMPT_DISCLOSURE_PATTERNS):
        return "block", "prompt_disclosure"
    if _matches_any(text, _JAILBREAK_PATTERNS):
        return "block", "jailbreak"
    if _matches_any(text, _UNSAFE_PATTERNS):
        return "block", "unsafe_content"
    return "allow", "ok"


# ── Output patterns ─────────────────────────────────────────────────

_OUTPUT_LEAK_PATTERNS = [
    r"system\s*prompt",
    r"OPENAI_API_KEY",
    r"SERPAPI_API_KEY",
    r"api_key\s*=",
    r"\.env\b",
    r"pydantic",
    r"BaseModel",
    r"TravelState",
    r"LangGraph",
    r"langgraph",
    r"langchain",
    r"structured_output",
    r"follow_up_questions",
    r"user_current_intent",
    r"safar_api\.",
    r"def\s+\w+_node\(",
    r"import\s+\w+",
]


def sanitize_output(text: str) -> str:
    """If the response contains leaked internals, replace it entirely."""
    if any(re.search(p, text, re.IGNORECASE) for p in _OUTPUT_LEAK_PATTERNS):
        return (
            "I can only share information about your trip. "
            "Is there anything about your travel plans I can help with?"
        )
    return text


# ── Graph node ───────────────────────────────────────────────────────

def guardrail_node(state: TravelState) -> dict:
    """Input guardrail — runs before intent classification."""
    latest = state.messages[-1]
    text = latest.content if hasattr(latest, "content") else str(latest)
    action, reason = check_input(text)

    if action == "block":
        return {
            "guardrail_action": action,
            "messages": [AIMessage(content=_BLOCK_RESPONSE)],
        }
    if action == "redirect":
        return {
            "guardrail_action": action,
            "messages": [AIMessage(content=_REDIRECT_RESPONSE)],
        }
    return {"guardrail_action": "allow"}


def guardrail_route(state: TravelState) -> str:
    action = getattr(state, "guardrail_action", "allow")
    if action in ("block", "redirect"):
        return "guardrail_respond"
    return "extract_user_intent"


def guardrail_respond(state: TravelState) -> dict:
    """Terminal node for blocked/redirected messages — just passes through."""
    return {}
