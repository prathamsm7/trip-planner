import re

TRANSPORT_BUNDLE = """
{source} to {destination} transport options flight train distance time,
nearest airport railway-station {destination},
nearest airport railway-station {source},
local transport in {destination} taxi rental availability
"""

ACTIVITIES_BUNDLE = """
things to do in {destination} {month} weather,
tourist attractions and places to visit in {destination},
nearby sightseeing and cultural places
"""


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"\[([^\]]+)\]", r"\1", text)
    text = re.sub(r"\(([^)]+)\)", r"\1", text)
    text = re.sub(r"[#>*`_~-]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
