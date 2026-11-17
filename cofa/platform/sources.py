"""Readers for the client's other systems: the bank's camt.054 files and the accounts-receivable mailbox."""
from __future__ import annotations

import email
import email.policy
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

NS = {"c": "urn:iso:std:iso:20022:tech:xsd:camt.054.001.08"}


def _cents(s: str) -> int:
    whole, _, frac = s.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


class Bank:
    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self._cache: dict[str, list[dict]] = {}

    def days(self) -> list[str]:
        return sorted(p.stem.split("_")[1] for p in self.folder.glob("camt054_*.xml"))

    def entries(self, day: str) -> list[dict]:
        if day not in self._cache:
            p = self.folder / f"camt054_{day}.xml"
            out = []
            if p.exists():
                for n in ET.parse(p).getroot().iterfind(".//c:Ntry", NS):
                    if n.findtext("c:CdtDbtInd", namespaces=NS) != "CRDT":
                        continue
                    tx = n.find(".//c:TxDtls", NS)
                    out.append({"entry_id": n.findtext("c:AcctSvcrRef", namespaces=NS), "day": day,
                                "amount_cents": _cents(n.findtext("c:Amt", namespaces=NS)),
                                "debtor_name": tx.findtext(".//c:Dbtr/c:Pty/c:Nm", namespaces=NS) or "",
                                "debtor_iban": tx.findtext(".//c:DbtrAcct/c:Id/c:IBAN", namespaces=NS) or "",
                                "reference": tx.findtext(".//c:RmtInf/c:Ustrd", namespaces=NS) or ""})
            self._cache[day] = out
        return self._cache[day]

    def search(self, iban: str | None = None, amount_cents: int | None = None, until: str | None = None) -> list[dict]:
        hits = []
        for d in self.days():
            if until and d > until:
                break
            hits += [e for e in self.entries(d) if (iban is None or e["debtor_iban"] == iban)
                     and (amount_cents is None or e["amount_cents"] == amount_cents)]
        return hits


class Mailbox:
    def __init__(self, folder: str | Path, outbox: str | Path | None = None):
        self.folder, self.outbox = Path(folder), Path(outbox) if outbox else None
        self._msgs: list[dict] | None = None

    def all(self) -> list[dict]:
        files = sorted(self.folder.glob("*.eml"))
        if self._msgs is None or len(self._msgs) != len(files):
            out = []
            for p in files:
                m = email.message_from_bytes(p.read_bytes(), policy=email.policy.default)
                out.append({"id": p.stem, "from": str(m["From"]), "subject": str(m["Subject"]),
                            "day": parsedate_to_datetime(m["Date"]).date().isoformat(),
                            "in_reply_to": str(m["In-Reply-To"] or "").strip("<>").split("@")[0],
                            "body": m.get_body(("plain",)).get_content()})
            self._msgs = out
        return self._msgs

    def received_until(self, day: str) -> list[dict]:
        return [m for m in self.all() if m["day"] <= day]

    def get(self, mid: str) -> dict | None:
        return next((m for m in self.all() if m["id"] == mid), None)

    def draft(self, to: str, subject: str, body: str, in_reply_to: str | None = None) -> dict:
        if not self.outbox:
            raise RuntimeError("no outbox configured")
        self.outbox.mkdir(parents=True, exist_ok=True)
        n = len(list(self.outbox.glob("*.txt"))) + 1
        p = self.outbox / f"draft_{n:04d}.txt"
        p.write_text(f"To: {to}\nSubject: {subject}\nIn-Reply-To: {in_reply_to or ''}\n\n{body}\n", encoding="utf-8")
        return {"draft": p.name}
