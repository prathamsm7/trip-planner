import re


def clean_text(text: str) -> str:
    """Strip markdown and URLs so search snippets are plain text."""
    if not text:
        return ""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"\[([^\]]+)\]", r"\1", text)
    text = re.sub(r"\(([^)]+)\)", r"\1", text)
    text = re.sub(r"[#>*`_~-]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
