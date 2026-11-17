"""Customer text is data. Paragraphs that address an AI or give the reader orders are split off before reading,
reported, and never used as facts."""
from __future__ import annotations

import re

PATTERNS = [r"\bignor\w*\b.*\b(regeln|rules|instructions|anweisungen)\b", r"\bdisregard\b", r"\[system\]",
            r"\b(ki|ai)[- ](assistent\w*|agent\w*|system\w*)\b", r"\bautomatische[n]? systeme\b",
            r"\bdo not route\b", r"\bverbuchen sie\b", r"\banweisung der geschäftsführung\b"]
RX = [re.compile(p, re.IGNORECASE) for p in PATTERNS]


def split_instructions(text: str) -> tuple[str, list[str]]:
    keep, flagged = [], []
    for para in re.split(r"\n\s*\n", text):
        (flagged if any(r.search(para) for r in RX) else keep).append(para)
    return "\n\n".join(keep), flagged
