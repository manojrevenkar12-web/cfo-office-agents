"""Engagement 1: cash application. Every incoming payment is matched to the open items it pays, and posted when
the evidence is complete; otherwise it goes to a person with a proposal and the evidence for it.

Three designs run on the same bank days:
- `erp_standard`: what the client's ERP does out of the box: an exact invoice number in the reference and the
  exact open amount, or nothing;
- `model_decides`: the advice and reference go to a model that is trusted with the decision (emulated: it follows
  what the text says, takes every deduction and the nearest match, and obeys instructions in the mail);
- `agent`: the platform's way: the model reads, code decides, identifiers decide and names only propose.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations

from cofa.platform.reader.base import Advice, AdviceLine
from cofa.platform.reader.rules import DOC

PO = re.compile(r"(?<!\d)45\d{8}(?!\d)")
AID = re.compile(r"\bPA-\d+\b")
ADVICE_WORDS = re.compile(r"avis|advice", re.I)
REASON_WORDS = {"price": ("preis", "price"), "damage": ("schaden", "beschädigt", "damaged"),
                "quantity": ("menge", "short delivery", "fehlmenge")}


def reason_class(note: str) -> str | None:
    low = note.lower()
    return next((k for k, ws in REASON_WORDS.items() if any(w in low for w in ws)), None)


def near(a: str, b: str) -> bool:
    """One substitution or one swap of neighbouring digits."""
    if len(a) != len(b) or a == b:
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])


@dataclass
class Decision:
    action: str                      # post | review | wait
    reason: str
    kunnr: str | None = None
    lines: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)


class CashApplication:
    engagement = "cash_application"

    def __init__(self, belt, reader, tracer, ops, settings: dict, design: str = "agent"):
        self.t, self.reader, self.tracer, self.ops, self.design = belt, reader, tracer, ops, design
        self.s = settings["cash_application"]
        self.used_mails: set[str] = set()
        self.waiting: dict[str, dict] = {}
        self.calendar: list[str] = []

    # ---------------- driver ----------------
    async def run(self, days: list[str]) -> dict:
        counts = {"post": 0, "review": 0, "wait": 0}
        for day in days:
            self.calendar.append(day)
            entries = list(self.waiting.values()) + (await self.t.call("bank", "entries", day=day))["entries"]
            self.waiting = {}
            for e in entries:
                age = len(self.calendar) - 1 - self.calendar.index(e["day"])
                with self.tracer.span("cash.decide", entry=e["entry_id"], design=self.design, day=day) as sp:
                    d = await self.decide(e, day, age)
                    sp.set_attribute("action", d.action)
                    sp.set_attribute("reason", d.reason)
                await self.act(e, d, day)
                counts[d.action] += 1
        return counts

    async def act(self, e: dict, d: Decision, day: str) -> None:
        if d.action == "wait":
            self.waiting[e["entry_id"]] = e
            return
        if d.action == "post":
            res = await self.t.call("erp", "post_clearing", payment_id=e["entry_id"], lines=d.lines,
                                    idempotency_key=f"{e['entry_id']}:{self.design}", posted_by=f"cash-agent/{self.design}", posted_on=day)
            if "rejected" in res:
                d = Decision("review", f"ERP refused the posting: {res['rejected']}", d.kunnr, d.lines, d.evidence)
            else:
                for b in d.blocks:
                    await self.t.call("erp", "block_dunning", **b)
        self.ops.decide(self.engagement, self.design, e["entry_id"], day, d.action, d.reason, d.kunnr, d.lines, d.evidence,
                        e["amount_cents"])

    async def decide(self, e: dict, day: str, age: int) -> Decision:
        if self.design == "erp_standard":
            return await self._standard(e)
        if self.design == "model_decides":
            return await self._model_decides(e, day, age)
        return await self._agent(e, day, age)

    # ---------------- shared lookups ----------------
    async def payer_scope(self, iban: str) -> list[str]:
        """Customers this IBAN may pay for, from master data only: its owners and the customers they pay for."""
        own = (await self.t.call("erp", "customers_by_iban", iban=iban))["kunnr"]
        scope = list(own)
        for k in own:
            scope += (await self.t.call("erp", "customer", kunnr=k)).get("paid_for", [])
        return list(dict.fromkeys(scope))

    async def items(self, docs: list[str]) -> dict[str, dict]:
        out = {}
        for d in docs:
            it = await self.t.call("erp", "item", doc=d)
            if "error" not in it:
                out[d] = it
        return out

    async def find_advice(self, e: dict, day: str, scope: list[str]) -> tuple[Advice | None, str | None]:
        aid = AID.search(e["reference"])
        msgs = (await self.t.call("mailbox", "received", until=day))["messages"]
        cands = [m for m in msgs if m["id"] not in self.used_mails and ADVICE_WORDS.search(m["subject"])
                 and (not aid or aid.group(0) in m["subject"])]
        for m in cands:
            body = (await self.t.call("mailbox", "message", mid=m["id"]))["body"]
            with self.tracer.span("reader.advice", reader=self.reader.name, mail=m["id"]) as sp:
                adv = self.reader.read_advice(body if self.design != "model_decides" else body)
                sp.set_attribute("tokens", adv.tokens)
                sp.set_attribute("lines", len(adv.lines))
            if sum(ln.paid_cents or 0 for ln in adv.lines) == e["amount_cents"] or aid:
                self.used_mails.add(m["id"])
                return adv, m["id"]
        return None, None

    # ---------------- erp_standard ----------------
    async def _standard(self, e: dict) -> Decision:
        docs = list(dict.fromkeys(DOC.findall(e["reference"])))
        its = await self.items(docs)
        if docs and len(its) == len(docs) and sum(i["remaining_cents"] for i in its.values()) == e["amount_cents"] \
                and all(i["remaining_cents"] != 0 for i in its.values()):
            return Decision("post", "invoice numbers and amount match exactly", its[docs[0]]["kunnr"],
                            [{"doc": d, "kind": "clear", "amount_cents": its[d]["remaining_cents"]} for d in docs])
        return Decision("review", "no exact match", None)

    # ---------------- agent ----------------
    async def _agent(self, e: dict, day: str, age: int) -> Decision:
        ev = []
        scope = await self.payer_scope(e["debtor_iban"])
        if scope:
            ev.append(f"IBAN belongs to {', '.join(scope[:3])} in the master data")
        ref = e["reference"]
        if AID.search(ref) or ADVICE_WORDS.search(ref):
            adv, mid = await self.find_advice(e, day, scope)
            if adv is None:
                if age < self.s["wait_for_advice_days"]:
                    return Decision("wait", "the reference announces a payment advice that has not arrived yet")
                return Decision("review", "payment advice announced but not received", scope[0] if scope else None, evidence=ev)
            ev.append(f"payment advice {mid} read by the {self.reader.name} reader")
            if adv.instructions:
                ev.append(f"the advice contained {len(adv.instructions)} paragraph(s) addressed to an AI; ignored and reported")
            return await self._from_lines(e, day, adv.lines, scope, ev)
        docs = list(dict.fromkeys(DOC.findall(ref)))
        if docs:
            its = await self.items(docs)
            cleared = [d for d, i in its.items() if i["remaining_cents"] == 0]
            if len(its) == len(docs) and not cleared:
                lines = [AdviceLine(d, its[d]["gross_cents"], 0, None) for d in docs]
                dec = await self._explain(e, day, its, lines, scope, ev + ["invoice numbers in the reference"], "skonto" in ref.lower())
                if dec.action == "post" or not dec.reason.startswith("open amount"):
                    return dec                                  # posted, or a specific reason a person must see
            # a reference that is not ours, or does not fit: one edit away, with the exact amount, in scope only
            if scope:
                opens = [i for k in scope for i in (await self.t.call("erp", "open_items", kunnr=k))["items"]]
                hits = [i for i in opens for d in docs if near(d, i["doc"]) and i["remaining_cents"] == e["amount_cents"]]
                if len(hits) == 1:
                    h = hits[0]
                    return Decision("post", f"reference {docs[0]} is one digit from {h['doc']}, same customer, exact amount",
                                    h["kunnr"], [{"doc": h["doc"], "kind": "clear", "amount_cents": h["remaining_cents"]}],
                                    ev + [f"{docs[0]} → {h['doc']}"])
            if cleared and len(cleared) == len(docs):
                return Decision("review", f"{', '.join(cleared)} already cleared: likely a second payment", scope[0] if scope else None,
                                [{"doc": None, "kind": "on_account", "amount_cents": e["amount_cents"]}], ev)
            return Decision("review", "invoice numbers in the reference do not fit the amount", scope[0] if scope else None,
                            dec.lines if len(its) == len(docs) and not cleared else [], ev)
        pos = PO.findall(ref)
        if pos:
            its = {}
            for p in pos:
                for i in (await self.t.call("erp", "items_by_po", po=p))["items"]:
                    its[i["doc"]] = i
            if its and sum(i["remaining_cents"] for i in its.values()) == e["amount_cents"] and \
                    (not scope or all(i["kunnr"] in scope for i in its.values())):
                k = next(iter(its.values()))["kunnr"]
                return Decision("post", "purchase order number and exact amount", k,
                                [{"doc": d, "kind": "clear", "amount_cents": i["remaining_cents"]} for d, i in its.items()],
                                ev + [f"PO {', '.join(pos)}"])
            return Decision("review", "purchase order number does not fit the amount", scope[0] if scope else None, evidence=ev)
        if scope:
            opens = [i for k in scope for i in (await self.t.call("erp", "open_items", kunnr=k))["items"] if i["remaining_cents"] > 0]
            fits = [c for n in range(1, self.s["max_subset"] + 1) for c in combinations(opens, n)
                    if sum(i["remaining_cents"] for i in c) == e["amount_cents"]]
            if len(fits) == 1:
                c = fits[0]
                return Decision("post", f"no reference; exactly one combination of open items ({len(c)}) gives the amount",
                                c[0]["kunnr"], [{"doc": i["doc"], "kind": "clear", "amount_cents": i["remaining_cents"]} for i in c],
                                ev + ["unique combination"])
            prop = [{"doc": i["doc"], "kind": "clear", "amount_cents": i["remaining_cents"]} for i in fits[0]] if fits else []
            return Decision("review", f"no reference; {len(fits)} combinations of open items give the amount", scope[0], prop, ev)
        words = [w for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", e["debtor_name"])][:2]
        names = (await self.t.call("erp", "search_customers", words=words))["customers"] if words else []
        return Decision("review", "unknown IBAN and no reference; a name match only proposes",
                        names[0]["kunnr"] if names else None, evidence=[f"name suggests {n['kunnr']} {n['name']}" for n in names])

    async def _from_lines(self, e, day, lines: list[AdviceLine], scope, ev) -> Decision:
        docs = [ln.doc for ln in lines]
        its = await self.items(docs)
        missing = [d for d in docs if d not in its]
        if missing:
            return Decision("review", f"advice names unknown documents {', '.join(missing)}", scope[0] if scope else None, evidence=ev)
        return await self._explain(e, day, its, lines, scope, ev, True)

    async def _explain(self, e, day, its: dict, lines: list[AdviceLine], scope, ev, skonto_hint: bool) -> Decision:
        """Turns lines into postings only if every cent is explained: the item is open, each deduction is a cash
        discount still allowed on the payment day or a deduction with a stated reason, and the lines add up to
        the payment. Customer: the IBAN's scope, or every document named explicitly with the exact amount."""
        owners = {i["kunnr"] for i in its.values()}
        kunnr = next(iter(owners))
        if any(ln.paid_cents is None for ln in lines):           # invoice numbers only: open amount, or less discount
            pcts = {d: await self._skonto_pct(its[d]["kunnr"]) for d in its}
            full = sum(its[ln.doc]["remaining_cents"] for ln in lines)
            discs = {ln.doc: (round(its[ln.doc]["gross_cents"] * pcts[ln.doc] / 100) if its[ln.doc]["kind"] == "invoice" else 0)
                     for ln in lines}
            if full == e["amount_cents"]:
                lines = [AdviceLine(ln.doc, its[ln.doc]["gross_cents"], 0, its[ln.doc]["remaining_cents"]) for ln in lines]
            elif any(discs.values()) and abs(full - sum(discs.values()) - e["amount_cents"]) <= self.s["skonto_tolerance_cents"] * len(lines):
                lines = [AdviceLine(ln.doc, its[ln.doc]["gross_cents"], discs[ln.doc], its[ln.doc]["remaining_cents"] - discs[ln.doc],
                                    "Skonto") for ln in lines]
            else:
                return Decision("review", f"open amount {full} and payment {e['amount_cents']} differ without a discount that fits",
                                kunnr, evidence=ev)
        out, blocks, total, late = [], [], 0, []
        for ln in lines:
            it = its[ln.doc]
            rem = it["remaining_cents"]
            if rem == 0:
                return Decision("review", f"{ln.doc} is already cleared: likely a second payment", kunnr,
                                [{"doc": None, "kind": "on_account", "amount_cents": e["amount_cents"]}], ev)
            if it["kind"] == "credit":
                out.append({"doc": ln.doc, "kind": "clear", "amount_cents": rem})
                total += rem
                continue
            paid, less = ln.paid_cents, ln.less_cents
            disc = round(it["gross_cents"] * (await self._skonto_pct(it["kunnr"])) / 100)
            if less == 0:
                if paid != rem:
                    return Decision("review", f"{ln.doc}: paid {paid} of {rem} open without a stated deduction", kunnr,
                                    evidence=ev)
                out.append({"doc": ln.doc, "kind": "clear", "amount_cents": paid})
            elif disc and abs(less - disc) <= self.s["skonto_tolerance_cents"] and paid + less == rem:
                if it["skonto_until"] and day <= it["skonto_until"]:
                    out += [{"doc": ln.doc, "kind": "clear", "amount_cents": paid},
                            {"doc": ln.doc, "kind": "skonto", "amount_cents": less}]
                else:
                    late.append(ln.doc)
                    out.append({"doc": ln.doc, "kind": "clear", "amount_cents": paid})
            elif paid + less == rem and reason_class(ln.note):
                out.append({"doc": ln.doc, "kind": "clear", "amount_cents": paid})
                blocks.append({"doc": ln.doc, "reason": f"deduction:{reason_class(ln.note)}", "note": ln.note[:80]})
            else:
                return Decision("review", f"{ln.doc}: deduction of {less} cents without a reason the policy accepts", kunnr,
                                evidence=ev)
            total += paid
        if total != e["amount_cents"]:
            return Decision("review", f"lines add up to {total}, the payment is {e['amount_cents']}", kunnr, out, ev)
        named = all(d in DOC.findall(e["reference"]) for d in its) or any("advice" in x for x in ev)
        if scope and not owners <= set(scope) and not named:
            return Decision("review", "documents belong to a customer this IBAN does not pay for", kunnr, out, ev)
        if not scope and not named:
            return Decision("review", "unknown IBAN", kunnr, out, ev)
        if late:
            return Decision("review", f"cash discount taken after its period on {', '.join(late)}", kunnr, out,
                            ev + ["proposal clears what was paid and leaves the discount open"])
        if len(owners) > 1 and not (scope and owners <= set(scope)):
            return Decision("review", "documents of several customers and no group relation in the master data", kunnr, out, ev)
        return Decision("post", "every cent explained", kunnr, out, ev + (["dunning blocked for deductions"] if blocks else []), blocks)

    async def _skonto_pct(self, kunnr: str) -> float:
        c = await self.t.call("erp", "customer", kunnr=kunnr)
        return float(c.get("skonto_pct") or 0)

    # ---------------- model_decides ----------------
    async def _model_decides(self, e: dict, day: str, age: int) -> Decision:
        """Emulates a model trusted with the decision: it applies what the text says. Instructions in the advice
        are followed, every deduction is accepted, the nearest invoice is taken, and names identify customers."""
        ref = e["reference"]
        if AID.search(ref) or ADVICE_WORDS.search(ref):
            msgs = (await self.t.call("mailbox", "received", until=day))["messages"]
            aid = AID.search(ref)
            for m in msgs:
                if m["id"] in self.used_mails or not ADVICE_WORDS.search(m["subject"]) or (aid and aid.group(0) not in m["subject"]):
                    continue
                body = (await self.t.call("mailbox", "message", mid=m["id"]))["body"]
                ordered = DOC.findall(body.split("\n\n")[-1]) if re.search(r"(?i)ignor|disregard|\[system\]", body) else []
                if ordered:
                    self.used_mails.add(m["id"])
                    it = await self.t.call("erp", "item", doc=ordered[-1])
                    take = max(0, min(it.get("remaining_cents", 0), e["amount_cents"]))
                    lines = [{"doc": ordered[-1], "kind": "clear", "amount_cents": take}] if take else []
                    if e["amount_cents"] > take:
                        lines.append({"doc": None, "kind": "on_account", "amount_cents": e["amount_cents"] - take})
                    return Decision("post", "the advice says to apply the payment to this invoice", it.get("kunnr"), lines)
                adv = self.reader.read_advice(body)
                if sum(ln.paid_cents or 0 for ln in adv.lines) == e["amount_cents"] or aid:
                    self.used_mails.add(m["id"])
                    its = await self.items([ln.doc for ln in adv.lines])
                    lines = []
                    for ln in adv.lines:
                        if ln.doc in its and its[ln.doc]["remaining_cents"]:
                            lines.append({"doc": ln.doc, "kind": "clear", "amount_cents": ln.paid_cents})
                            if ln.less_cents and its[ln.doc]["kind"] == "invoice":
                                lines.append({"doc": ln.doc, "kind": "skonto", "amount_cents": ln.less_cents})
                    return Decision("post", "applied as the advice says", None, lines)
            return Decision("wait" if age < 1 else "review", "advice not found")
        docs = list(dict.fromkeys(DOC.findall(ref)))
        if docs:
            its = await self.items(docs)
            if its:
                left, lines = e["amount_cents"], []
                for d, it in its.items():
                    if it["remaining_cents"] <= 0:
                        continue
                    take = min(it["remaining_cents"], left)
                    lines.append({"doc": d, "kind": "clear", "amount_cents": take})
                    if take < it["remaining_cents"] and it["kind"] == "invoice":
                        lines.append({"doc": d, "kind": "skonto", "amount_cents": it["remaining_cents"] - take})
                    left -= take
                if lines:
                    return Decision("post", "invoice numbers in the reference", None, lines)
        scope = await self.payer_scope(e["debtor_iban"])
        if not scope:
            words = [w for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", e["debtor_name"])][:1]
            scope = [c["kunnr"] for c in (await self.t.call("erp", "search_customers", words=words))["customers"][:1]] if words else []
        opens = [i for k in scope for i in (await self.t.call("erp", "open_items", kunnr=k))["items"] if i["remaining_cents"] > 0]
        if docs and opens:
            best = min(opens, key=lambda i: sum(a != b for a, b in zip(i["doc"], docs[0])))
            return Decision("post", "closest invoice number", best["kunnr"],
                            [{"doc": best["doc"], "kind": "clear", "amount_cents": min(best["remaining_cents"], e["amount_cents"])}])
        if opens:
            left, lines = e["amount_cents"], []
            for i in sorted(opens, key=lambda i: i["doc_date"]):
                if left <= 0:
                    break
                take = min(i["remaining_cents"], left)
                lines.append({"doc": i["doc"], "kind": "clear", "amount_cents": take})
                left -= take
            if left > 0:
                lines.append({"doc": None, "kind": "on_account", "amount_cents": left})
            return Decision("post", "oldest open items of the customer", opens[0]["kunnr"], lines)
        return Decision("review", "nothing found")
