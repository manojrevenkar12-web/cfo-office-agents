"""An offline reader: patterns for document numbers, the three amount formats customers use, dates and a small
vocabulary in German and English. It needs no model and no network, so it runs in CI and in air-gapped client
environments; the Claude reader replaces it where a model is allowed."""
from __future__ import annotations

import re

from cofa.platform.guard import split_instructions
from cofa.platform.reader.base import Advice, AdviceLine, ReplyRead

DOC = re.compile(r"(?<!\d)9[01]\d{6}(?!\d)")
DATE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b|(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
AMT_DE = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}(?!\d)")
AMT_EN = re.compile(r"-?\d{1,3}(?:,\d{3})+\.\d{2}(?!\d)|-?\d+\.\d{2}(?!\d)")
STOP = {"rechnung", "vom", "eur", "abzgl", "gezahlt", "invoice", "beleg", "skonto"}


def cents(s: str) -> int:
    neg = s.startswith("-")
    digits = re.sub(r"[^\d]", "", s)
    return (-1 if neg else 1) * int(digits)


def _amounts(seg: str) -> list[int]:
    seg = DATE.sub(" ", DOC.sub(" ", seg))
    found = AMT_DE.findall(seg) if re.search(r"\d,\d{2}(?!\d)", seg) else AMT_EN.findall(seg)
    return [cents(a) for a in found]


def _note(seg: str) -> str:
    seg = DATE.sub(" ", DOC.sub(" ", seg))
    words = [w for w in re.findall(r"[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß.-]*", seg) if w.lower().strip(".") not in STOP]
    return " ".join(w for w in words if not w.isupper() or len(w) > 4)[:80]


class RuleReader:
    name = "rules"

    def read_advice(self, text: str) -> Advice:
        data, flagged = split_instructions(text)
        segments = [s for ln in data.splitlines() for s in ln.split(";")]
        lines, total = [], None
        for seg in segments:
            docs = DOC.findall(seg)
            if len(docs) != 1:
                if re.search(r"\b(summe|total|gesamt)\b", seg, re.I):
                    a = _amounts(seg)
                    total = a[-1] if a else total
                continue
            seg = seg[seg.index(docs[0]):]                    # amounts and notes come after the document number
            a = _amounts(seg)
            if not a:
                continue
            if len(a) >= 3:
                gross, less, paid = a[0], a[1], a[2]
            elif len(a) == 2:
                gross, paid = a[0], a[1]
                less = gross - paid
            else:
                gross, less, paid = a[0], 0, a[0]
            lines.append(AdviceLine(docs[0], gross, less, paid, _note(seg) if less else ""))
        return Advice(lines, total, flagged)

    def read_reply(self, text: str) -> ReplyRead:
        data, flagged = split_instructions(text)
        low = data.lower()
        docs = list(dict.fromkeys(DOC.findall(data)))
        d = None
        m = DATE.search(data)
        if m:
            g = m.groups()
            d = f"{g[2]}-{g[1]}-{g[0]}" if g[0] else (f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[6]}-{g[7]}-{g[8]}")
        if any(k in low for k in ("strittig", "disputed", "gutschrift", "credit note")):
            intent = "dispute"
        elif any(k in low for k in ("kopie", "copy", "nicht vor", "cannot find")):
            intent = "invoice_copy"
        elif any(k in low for k in ("begleichen", "will settle", "werden die rechnung")):
            intent = "promise_to_pay"
        elif any(k in low for k in ("bezahlt", "überwiesen", "paid")):
            intent = "says_paid"
        else:
            intent = "other"
        reason = None
        if intent == "dispute":
            reason = ("price" if any(k in low for k in ("preis", "price")) else
                      "damage" if any(k in low for k in ("beschädigt", "schaden", "damaged")) else
                      "quantity" if any(k in low for k in ("menge", "short delivery", "fehlmenge")) else "other")
        return ReplyRead(intent, docs, d if intent in ("promise_to_pay", "says_paid") else None, reason, flagged)
