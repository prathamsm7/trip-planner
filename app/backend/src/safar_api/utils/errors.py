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
    if "no interrupt" in lower:
        return "Please send your answer in the chat so I can continue planning."

    if len(raw) > 160:
        return "Something went wrong while processing your request. Please try again."

    return raw.strip() or "Something went wrong. Please try again."
