"""Connector to the client's ERP (accounts receivable): customer master, open items, postings, dunning.

Every write is idempotent: a posting carries a key, and the same key never posts twice. A clearing posts only
when it fits what is still open on each item, in one transaction."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


class PostingRejected(Exception):
    pass


class Erp:
    def __init__(self, db: str | Path):
        self.db = str(db)

    def _c(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    # ---- reads ----
    def customer(self, kunnr: str) -> dict | None:
        with closing(self._c()) as c:
            row = c.execute("select * from customers where kunnr = ?", (kunnr,)).fetchone()
            if not row:
                return None
            out = dict(row)
            out["ibans"] = [r[0] for r in c.execute("select iban from customer_ibans where kunnr = ?", (kunnr,))]
            out["paid_for"] = [r[0] for r in c.execute("select kunnr from customers where payer_kunnr = ?", (kunnr,))]
            return out

    def customers_by_iban(self, iban: str) -> list[str]:
        with closing(self._c()) as c:
            return [r[0] for r in c.execute("select kunnr from customer_ibans where iban = ?", (iban,))]

    def search_customers(self, words: list[str], limit: int = 5) -> list[dict]:
        """Customers whose name contains every word (case-insensitive, umlauts folded). Names only propose."""
        fold = lambda s: s.lower().replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")  # noqa: E731
        ws = [fold(w) for w in words if len(w) > 2]
        with closing(self._c()) as c:
            rows = [dict(r) for r in c.execute("select kunnr, name, city from customers")]
        return [r for r in rows if ws and all(w in fold(r["name"]) for w in ws)][:limit]

    def _remaining(self, c, doc: str) -> int:
        gross = c.execute("select gross_cents from items where doc = ?", (doc,)).fetchone()[0]
        done = c.execute("select coalesce(sum(amount_cents), 0) from postings where doc = ? and kind in ('clear','skonto','deduction')",
                         (doc,)).fetchone()[0]
        return gross - done

    def item(self, doc: str) -> dict | None:
        with closing(self._c()) as c:
            row = c.execute("select * from items where doc = ?", (doc,)).fetchone()
            if not row:
                return None
            out = dict(row)
            out["remaining_cents"] = self._remaining(c, doc)
            out["blocked"] = c.execute("select reason, until from dunning_blocks where doc = ?", (doc,)).fetchone() is not None
            return out

    def open_items(self, kunnr: str) -> list[dict]:
        with closing(self._c()) as c:
            docs = [r[0] for r in c.execute("select doc from items where kunnr = ? order by doc_date, doc", (kunnr,))]
        items = [self.item(d) for d in docs]
        return [i for i in items if i["remaining_cents"] != 0]

    def items_by_po(self, po: str) -> list[dict]:
        with closing(self._c()) as c:
            docs = [r[0] for r in c.execute("select doc from items where po = ?", (po,))]
        return [self.item(d) for d in docs]

    def postings(self, payment_id: str | None = None) -> list[dict]:
        with closing(self._c()) as c:
            q = "select * from postings" + (" where payment_id = ?" if payment_id else "") + " order by id"
            return [dict(r) for r in c.execute(q, (payment_id,) if payment_id else ())]

    # ---- writes ----
    def post(self, payment_id: str, lines: list[dict], key: str, by: str, on: str) -> dict:
        """Posts the lines of one payment atomically. Each line: doc (or None for on-account), kind, amount_cents,
        reason. Returns {"posted": n} or {"duplicate": true} when the key was used before."""
        with closing(self._c()) as c:
            if c.execute("select 1 from postings where idem_key like ?", (key + "#%",)).fetchone():
                return {"duplicate": True, "posted": 0}
            try:
                c.execute("begin immediate")
                for n, ln in enumerate(lines):
                    if ln.get("doc"):
                        if not c.execute("select 1 from items where doc = ?", (ln["doc"],)).fetchone():
                            raise PostingRejected(f"unknown item {ln['doc']}")
                        rem = self._remaining(c, ln["doc"])
                        if (rem > 0 and ln["amount_cents"] > rem) or (rem < 0 and ln["amount_cents"] < rem) or rem == 0:
                            raise PostingRejected(f"item {ln['doc']} has {rem} cents open, line wants {ln['amount_cents']}")
                    c.execute("insert into postings (payment_id, doc, kind, amount_cents, reason, idem_key, posted_by, posted_on) "
                              "values (?,?,?,?,?,?,?,?)", (payment_id, ln.get("doc"), ln["kind"], ln["amount_cents"],
                                                           ln.get("reason"), f"{key}#{n}", by, on))
                c.commit()
            except Exception:
                c.rollback()
                raise
        return {"duplicate": False, "posted": len(lines)}

    def record_dunning(self, letter_id: str, kunnr: str, docs: list[str], level: int, on: str) -> dict:
        with closing(self._c()) as c:
            c.execute("insert or ignore into dunning values (?,?,?,?,?)", (letter_id, kunnr, ",".join(docs), level, on))
            c.commit()
        return {"letter_id": letter_id}

    def block_dunning(self, doc: str, reason: str, until: str | None, note: str) -> dict:
        with closing(self._c()) as c:
            c.execute("insert or replace into dunning_blocks values (?,?,?,?)", (doc, reason, until, note))
            c.commit()
        return {"doc": doc, "reason": reason}

    def dunning_letters(self) -> list[dict]:
        with closing(self._c()) as c:
            return [dict(r) for r in c.execute("select * from dunning")]

    def overdue(self, on: str) -> list[dict]:
        with closing(self._c()) as c:
            docs = [r[0] for r in c.execute("select doc from items where kind = 'invoice' and due < ?", (on,))]
        return [i for i in (self.item(d) for d in docs) if i["remaining_cents"] > 0]
