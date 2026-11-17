"""The whole evaluation: build the client, run every design of both engagements on its own copy of the client's
ERP, score against the truth, measure the readers, and write the report."""
from __future__ import annotations

import asyncio
import email
import email.policy
import json
import shutil
import sqlite3
import time
from pathlib import Path

import yaml

from cofa.engagements.cash_application import CashApplication
from cofa.engagements.collections import Collections
from cofa.eval import score
from cofa.platform.erp import Erp
from cofa.platform.mcp_servers import bank_server, erp_server, mailbox_server
from cofa.platform.ops import Ops
from cofa.platform.reader.rules import RuleReader
from cofa.platform.tools import ToolBelt
from cofa.platform.trace import Tracer, summarise
from cofa.world.client import build, load, respond

ROOT = Path(__file__).resolve().parents[2]
RUNS = [  # (name, cash design, collections design)
    ("status_quo", "erp_standard", "standard"),
    ("model_decides", "model_decides", "standard"),
    ("platform", "agent", "agent"),
]


def settings() -> dict:
    return yaml.safe_load((ROOT / "config/product.yaml").read_text())


def reader(s: dict):
    if s["reader"] == "claude":
        from cofa.platform.reader.claude import ClaudeReader
        return ClaudeReader(s["claude"]["model"], s["claude"]["max_tokens"])
    return RuleReader()


async def run_design(cfg: dict, world: Path, out: Path, name: str, cash_design: str, coll_design: str, truth: dict, s: dict) -> dict:
    shutil.rmtree(out, ignore_errors=True)
    (out / "client").mkdir(parents=True)
    shutil.copy(world / "client" / "erp.sqlite", out / "client" / "erp.sqlite")
    shutil.copytree(world / "client" / "mail", out / "client" / "mail")
    srv = {"erp": erp_server(out / "client" / "erp.sqlite"), "bank": bank_server(world / "client" / "bank"),
           "mailbox": mailbox_server(out / "client" / "mail", out / "outbox")}
    tracer, ops, rd = Tracer(f"cofa-{name}"), Ops(out / "ops.sqlite"), reader(s)
    days = truth["days"]
    dun = days.index(truth["dunning_day"])
    t0 = time.time()
    async with ToolBelt(srv, tracer, name) as belt:
        cash = CashApplication(belt, rd, tracer, ops, s, cash_design)
        coll = Collections(belt, rd, tracer, ops, s, coll_design, cash_design)
        counts = await cash.run(days[:dun + 1])
        letters = await coll.dunning_run(days[dun])
        replies_sent = respond(cfg, world, out / "client" / "mail",
                               [{"letter_id": lid, "kunnr": v["kunnr"], "docs": v["docs"]} for lid, v in coll.letters.items()])
        replies = {}
        for i in range(dun + 1, len(days)):
            more = await cash.run([days[i]])
            counts = {k: counts.get(k, 0) + more.get(k, 0) for k in set(counts) | set(more)}
            for k, v in (await coll.replies(days[i])).items():
                replies[k] = replies.get(k, 0) + v
        calls = belt.calls
    seconds = time.time() - t0
    db = sqlite3.connect(out / "client" / "erp.sqlite")
    blocks = {d: (r, u) for d, r, u in db.execute("select doc, reason, until from dunning_blocks")}
    letters_rows = [dict(zip(("letter_id", "kunnr", "docs", "level", "sent_on"), r)) for r in db.execute("select * from dunning")]
    db.close()
    tracer.write(out / "traces.jsonl")
    recs = tracer.records()
    m = s["review_minutes"]
    c = score.cash(truth, Erp(out / "client" / "erp.sqlite").postings(), ops.decisions("cash_application", cash_design),
                   {d: v[0] for d, v in blocks.items()}, m, days[-1])
    k = score.collections(truth, letters_rows, replies_sent, blocks, ops.decisions("collections", coll_design), m)
    return {"cash_design": cash_design, "collections_design": coll_design, "cash": c, "collections": k,
            "letters_run": letters, "reply_actions": replies, "decision_counts": counts, "tool_calls": calls,
            "seconds": round(seconds, 1),
            "traces": {"cash": summarise(recs, "cash.decide"), "replies": summarise(recs, "collections.reply")}}


def reader_evals(cfg: dict, world: Path, truth: dict, rd) -> dict:
    """The reader measured on its own, from the mails and the truth: advice lines exactly right, reply intent right."""
    pays = {p["pid"]: p for p in truth["payments"]}
    want_intent = {"promise_to_pay": "promise_to_pay", "dispute": "dispute", "invoice_copy": "invoice_copy",
                   "claims_paid_not_true": "says_paid", "paid_unapplied": "says_paid"}
    adv = adv_ok = rep = rep_ok = inj = inj_flagged = 0
    box = world / "reader-eval-mail"
    shutil.rmtree(box, ignore_errors=True)
    shutil.copytree(world / "client" / "mail", box)
    every = {}
    for sit in truth["situations"]:
        every.setdefault(sit["kunnr"], set()).update(sit["docs"])
    replies = respond(cfg, world, box, [{"letter_id": f"MAHN-{k}", "kunnr": k, "docs": sorted(v)} for k, v in every.items()])
    for m in truth["mails"] + replies:
        raw = (box / f"{m['id']}.eml").read_bytes()
        body = email.message_from_bytes(raw, policy=email.policy.default).get_body(("plain",)).get_content()
        if m["kind"] == "advice":
            a = rd.read_advice(body)
            got = {(ln.doc, ln.paid_cents, ln.less_cents) for ln in a.lines}
            want = {(x["doc"], x["paid_cents"], x["skonto_cents"] + x["deduction_cents"]) for x in pays[m["payment"]]["allocations"]}
            adv += 1
            adv_ok += got == want
            if m.get("injection_doc"):
                inj += 1
                inj_flagged += bool(a.instructions) and m["injection_doc"] not in {ln.doc for ln in a.lines}
        else:
            r = rd.read_reply(body)
            rep += 1
            rep_ok += r.intent == want_intent[m["situation"]]
    return {"reader": rd.name, "advices": adv, "advices_exact": adv_ok, "advice_exact_share": round(adv_ok / max(1, adv), 4),
            "replies": rep, "reply_intent_right": rep_ok, "reply_intent_share": round(rep_ok / max(1, rep), 4),
            "injections": inj, "injections_flagged_and_ignored": inj_flagged}


def reuse() -> dict:
    """How much of each engagement is the shared platform: lines of code (no blanks, comments or docstrings)."""
    def loc(p: Path) -> int:
        n, doc = 0, False
        for ln in p.read_text().splitlines():
            s = ln.strip()
            if s.startswith('"""') or s.startswith("'''"):
                doc = not doc if s.count('"""') + s.count("'''") == 1 else doc
                continue
            if doc or not s or s.startswith("#"):
                continue
            n += 1
        return n
    plat = sum(loc(p) for p in (ROOT / "cofa/platform").rglob("*.py"))
    cash = loc(ROOT / "cofa/engagements/cash_application.py")
    coll = loc(ROOT / "cofa/engagements/collections.py")
    return {"platform_loc": plat, "cash_application_loc": cash, "collections_loc": coll,
            "collections_new_share": round(coll / (coll + plat), 3)}


def evaluate(world_file: str = "config/world.yaml", quick: bool = False, log=print, keep: bool = False) -> dict:
    cfg = load(ROOT / world_file)
    if quick:
        cfg = {**cfg, "customers": 30, "bank_days": 12, "collections": {**cfg["collections"], "dunning_day": 8}}
    work = ROOT / "work" / (cfg["name"] + ("-quick" if quick else ""))
    shutil.rmtree(work, ignore_errors=True)
    planted = build(cfg, work / "world")
    truth = json.loads((work / "world" / "truth" / "truth.json").read_text())
    s = settings()
    log(f"client built: {planted['payments']} payments, {planted['advice_mails']} advices")
    rep = {"world": cfg["name"], "company": cfg["company"]["name"], "quick": quick, "planted": planted, "runs": {},
           "readers": reader_evals(cfg, work / "world", truth, reader(s)), "reuse": reuse(),
           "period": {"from": truth["days"][0], "to": truth["days"][-1], "bank_days": len(truth["days"]),
                      "dunning_day": truth["dunning_day"]}}
    for name, cd, kd in RUNS:
        rep["runs"][name] = asyncio.run(run_design(cfg, work / "world", work / name, name, cd, kd, truth, s))
        r = rep["runs"][name]
        log(f"{name}: posted right {r['cash']['posted_right_share']}, wrong {r['cash']['posted_wrong']}, "
            f"letters to payers {r['collections']['letters_to_customers_who_had_paid']}, {r['seconds']} s")
    rep["business_case"] = business_case(rep, s)
    if not keep:
        for name, _, _ in RUNS:
            for f in ("ops.sqlite", "client", "outbox"):
                p = work / name / f
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    return rep


def business_case(rep: dict, s: dict) -> dict:
    base, plat = rep["runs"]["status_quo"], rep["runs"]["platform"]
    mins = lambda r: r["cash"]["clerk_minutes"] + r["collections"]["clerk_minutes"]  # noqa: E731
    saved_h = (mins(base) - mins(plat)) / 60
    days = rep["period"]["bank_days"]
    per_month = saved_h * 21 / days
    return {"clerk_hours_status_quo": round(mins(base) / 60, 1), "clerk_hours_platform": round(mins(plat) / 60, 1),
            "clerk_hours_saved_per_month": round(per_month, 1),
            "platform_hours_share": round(mins(plat) / mins(base), 3) if mins(base) else None,
            "eur_saved_per_year": int(round(per_month * 12 * s["clerk_cost_eur_per_hour"], -2)),
            "letters_to_paying_customers_avoided": base["collections"]["letters_to_customers_who_had_paid"]
            - plat["collections"]["letters_to_customers_who_had_paid"]}


def write_report(rep: dict, name: str) -> Path:
    out = ROOT / "reports" / f"{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, default=str) + "\n")
    return out
