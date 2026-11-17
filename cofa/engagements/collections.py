"""Engagement 2: collections, built on the same platform as cash application: the same MCP servers, reader,
guard, tracing and review queue. Two things are new: the dunning run, and reading the replies.

- `standard`: the ERP's dunning run: every overdue item gets a letter; every reply goes to a person.
- `agent`: no letter for money that has arrived but is not applied yet (the cash-application review queue says
  so); replies are read by the model, and code decides: a promise blocks dunning until its date, a dispute blocks
  the item with its reason, "already paid" is checked against the bank before anything is blocked, and every
  answer is a draft for a person to send, with the numbers taken from the ERP.
"""
from __future__ import annotations

from collections import defaultdict


def dmy(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def eur(c: int) -> str:
    return f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d} EUR"


TEMPLATES = {
    "promise": {"de": "vielen Dank für Ihre Nachricht. Wir haben Ihre Zahlungszusage für {docs} bis zum {date_de} vermerkt "
                      "und die Mahnung bis dahin ausgesetzt.",
                "en": "thank you for your message. We have noted your commitment to pay {docs} by {date} and suspended "
                      "the reminder until then."},
    "dispute": {"de": "vielen Dank für Ihre Rückmeldung zu Rechnung {docs}. Wir haben die Mahnung ausgesetzt und klären den "
                      "Sachverhalt; Sie hören in Kürze von uns.",
                "en": "thank you for your feedback on invoice {docs}. We have suspended the reminder and are looking into "
                      "it; you will hear from us shortly."},
    "copy": {"de": "anbei erhalten Sie die gewünschten Rechnungskopien:\n{lines}\n(Anlagen: PDF der Rechnungen {docs})",
             "en": "please find the requested invoice copies attached:\n{lines}\n(Attachments: PDF of invoices {docs})"},
    "paid_found": {"de": "vielen Dank. Wir haben Ihre Zahlung über {amount} vom {paid_de} gefunden und ordnen sie den Rechnungen "
                         "{docs} zu. Bitte betrachten Sie die Mahnung als gegenstandslos.",
                   "en": "thank you. We have found your payment of {amount} on {paid} and are applying it to invoices {docs}. "
                         "Please disregard the reminder."},
    "paid_not_found": {"de": "vielen Dank für Ihre Nachricht. Für die Rechnung(en) {docs} konnten wir bisher keinen Zahlungseingang "
                             "feststellen. Bitte senden Sie uns einen Zahlungsnachweis (Datum, Betrag, Konto).",
                       "en": "thank you for your message. We have not yet received a payment for invoice(s) {docs}. Please "
                             "send us proof of payment (date, amount, account)."},
}
FRAME = {"de": ("Sehr geehrte Damen und Herren,", "Mit freundlichen Grüßen\nDebitorenbuchhaltung"),
         "en": ("Dear Sir or Madam,", "Kind regards\nAccounts Receivable")}


class Collections:
    engagement = "collections"

    def __init__(self, belt, reader, tracer, ops, settings: dict, design: str = "agent", cash_design: str = "agent"):
        self.t, self.reader, self.tracer, self.ops, self.design, self.cash_design = belt, reader, tracer, ops, design, cash_design
        self.letters: dict[str, dict] = {}
        self.handled: set[str] = set()

    async def dunning_run(self, day: str) -> dict:
        overdue = (await self.t.call("erp", "overdue_items", on=day))["items"]
        held_docs, held_customers = set(), set()
        if self.design == "agent":
            for q in self.ops.queue("cash_application", self.cash_design):
                docs = [ln["doc"] for ln in q["proposal"] if ln.get("doc")]
                held_docs |= set(docs)
                if not docs and q["kunnr"]:
                    held_customers.add(q["kunnr"])
        by_customer = defaultdict(list)
        skipped = 0
        for it in overdue:
            if it["blocked"] or it["doc"] in held_docs or it["kunnr"] in held_customers:
                skipped += 1
                continue
            by_customer[it["kunnr"]].append(it)
        for k, items in by_customer.items():
            lid = f"MAHN-{k}"
            with self.tracer.span("collections.letter", letter=lid, design=self.design):
                await self.t.call("erp", "record_dunning", letter_id=lid, kunnr=k, docs=[i["doc"] for i in items], level=1, on=day)
            self.letters[lid] = {"kunnr": k, "docs": [i["doc"] for i in items], "items": {i["doc"]: i for i in items}}
        self.ops.decide(self.engagement, self.design, f"dunning-{day}", day, "post",
                        f"{len(by_customer)} letters, {skipped} items held back", evidence=[f"{len(held_docs)} items with money in review"])
        return {"letters": len(by_customer), "held_back": skipped}

    async def replies(self, day: str) -> dict:
        msgs = (await self.t.call("mailbox", "received", until=day))["messages"]
        mine = [m for m in msgs if m["in_reply_to"] in self.letters and m["id"] not in self.handled]
        counts = defaultdict(int)
        for m in mine:
            self.handled.add(m["id"])
            letter = self.letters[m["in_reply_to"]]
            with self.tracer.span("collections.reply", mail=m["id"], design=self.design) as sp:
                if self.design != "agent":
                    self.ops.decide(self.engagement, self.design, m["id"], day, "review", "reply to a dunning letter", letter["kunnr"])
                    counts["review"] += 1
                    continue
                body = (await self.t.call("mailbox", "message", mid=m["id"]))["body"]
                with self.tracer.span("reader.reply", reader=self.reader.name) as rs:
                    r = self.reader.read_reply(body)
                    rs.set_attribute("tokens", r.tokens)
                    rs.set_attribute("intent", r.intent)
                action = await self._act(m, letter, r, day)
                sp.set_attribute("action", action)
                counts[action] += 1
        return dict(counts)

    async def _act(self, m: dict, letter: dict, r, day: str) -> str:
        k = letter["kunnr"]
        docs = [d for d in r.docs if d in letter["docs"]] or letter["docs"]
        cust = await self.t.call("erp", "customer", kunnr=k)
        to = m["from"]
        subj = f"AW: {m['subject']}"
        if r.intent == "promise_to_pay" and r.date:
            for d in docs:
                await self.t.call("erp", "block_dunning", doc=d, reason="promise", until=r.date, note=m["id"])
            await self._draft(to, subj, "promise", m, docs=", ".join(docs), date=r.date, date_de=dmy(r.date))
            self.ops.decide(self.engagement, self.design, m["id"], day, "post", "promise recorded", k, [{"docs": docs, "until": r.date}])
            return "promise"
        if r.intent == "dispute":
            reason = f"dispute:{r.reason_class or 'other'}"
            for d in docs:
                await self.t.call("erp", "block_dunning", doc=d, reason=reason, note=m["id"])
            await self._draft(to, subj, "dispute", m, docs=", ".join(docs))
            self.ops.decide(self.engagement, self.design, m["id"], day, "review", f"dispute ({r.reason_class}) for a person", k,
                            [{"docs": docs, "reason": reason}])
            return "dispute"
        if r.intent == "invoice_copy":
            lines = "\n".join(f"- Rechnung {d}: {eur(letter['items'][d]['remaining_cents'])}" for d in docs if d in letter["items"])
            await self._draft(to, subj, "copy", m, docs=", ".join(docs), lines=lines)
            self.ops.decide(self.engagement, self.design, m["id"], day, "post", "invoice copy drafted", k, [{"docs": docs}])
            return "copy"
        if r.intent == "says_paid":
            found = await self._find_payment(k, cust, docs, letter, day)
            if found:
                for d in docs:
                    await self.t.call("erp", "block_dunning", doc=d, reason="payment_found", note=found["entry_id"])
                await self._draft(to, subj, "paid_found", m, docs=", ".join(docs), amount=eur(found["amount_cents"]),
                                  paid=found["day"], paid_de=dmy(found["day"]))
                self.ops.decide(self.engagement, self.design, m["id"], day, "review", "payment found in the bank; apply it", k,
                                [{"docs": docs, "entry": found["entry_id"]}])
                return "paid_found"
            await self._draft(to, subj, "paid_not_found", m, docs=", ".join(docs))
            self.ops.decide(self.engagement, self.design, m["id"], day, "post", "no payment found; proof requested, dunning continues", k,
                            [{"docs": docs}])
            return "paid_not_found"
        self.ops.decide(self.engagement, self.design, m["id"], day, "review", "reply not understood", k)
        return "review"

    async def _find_payment(self, k, cust, docs, letter, day) -> dict | None:
        want = sum(letter["items"][d]["remaining_cents"] for d in docs if d in letter["items"])
        ibans = list(cust.get("ibans", []))
        for kk in [x for x in [cust.get("payer_kunnr")] if x]:
            ibans += (await self.t.call("erp", "customer", kunnr=kk)).get("ibans", [])
        for iban in ibans:
            for e in (await self.t.call("bank", "search", iban=iban, until=day))["entries"]:
                if abs(e["amount_cents"] - want) > max(2, want // 50):        # the amount, or the amount less a discount
                    continue
                used = (await self.t.call("erp", "postings", payment_id=e["entry_id"]))["postings"]
                if not used or {p["doc"] for p in used} & set(docs):            # unapplied, or applied to these items
                    return e
        return None

    async def _draft(self, to, subject, template: str, m, **args) -> None:
        """Replies in the customer's language. The text is a fixed template; only numbers from the ERP and the bank
        are filled in, so a draft never states something the systems do not."""
        body = (await self.t.call("mailbox", "message", mid=m["id"]))["body"]
        lang = "en" if body.lstrip().startswith("Dear") else "de"
        greet, close = FRAME[lang]
        text = TEMPLATES[template][lang].format(**args)
        await self.t.call("mailbox", "draft_reply", to=to, subject=subject, body=f"{greet}\n\n{text}\n\n{close}", in_reply_to=m["id"])
