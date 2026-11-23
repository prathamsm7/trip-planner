import re


def friendly_error(exc: BaseException) -> str:
    """User-safe error text — never expose API keys or raw URLs."""
    raw = str(exc)

    raw = re.sub(r"api_key=[^&\s'\"]+", "api_key=***", raw, flags=re.I)
    raw = re.sub(r"https?://\S+", "", raw)

    lower = raw.lower()

    if "400" in raw and ("flight" in lower or "google_flights" in lower):
        return (
            "I couldn't search flights yet. Please plan your trip with travel dates first, "
            "then ask me to find flights."
        )
    if "serpapi" in lower or "api_key" in lower:
        return "Travel search is temporarily unavailable. Please try again shortly."
    if "tuple" in lower and "keys" in lower:
        return (
            "I hit an issue preparing your trip. Please add destination and dates, "
            "or try your request again."
        )
    if "no tool output found" in lower or "unboundlocalerror" in lower or "cannot access local variable" in lower:
        return "I lost the last step. Please send that request again."
    if "toolmessage" in lower and "command.update" in lower:
        return (
            "I hit an issue coordinating tools for that request. "
            "Please try again in a moment."
        )

    cleaned = raw.strip()
    if len(cleaned) > 220:
        return cleaned[:217].rstrip() + "..."
    return cleaned or "Something went wrong. Please try again."
