"""The console's API. It runs the platform on a client (the quick demo client by default) and lets a person work
the review queue: accepting a proposal posts it through the same ERP MCP server the agents use, idempotently.

    python -m cofa.service.api            # http://localhost:8080, the console from web/dist if built
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cofa.engagements.cash_application import CashApplication
from cofa.engagements.collections import Collections
from cofa.platform.mcp_servers import bank_server, erp_server, mailbox_server
from cofa.platform.ops import Ops
from cofa.platform.reader.rules import RuleReader
from cofa.platform.sources import Bank
from cofa.platform.tools import ToolBelt
from cofa.platform.trace import Tracer

ROOT = Path(__file__).resolve().parents[2]


class Engagement:
    """One client with the platform's agents run over its period, and the state a person then works on."""

    def __init__(self, client: Path, run: Path, settings: dict):
        self.client, self.run, self.s = client, run, settings
        self.ops = Ops(run / "ops.sqlite")
        self.tracer = Tracer("cofa-console")
        self.servers = {"erp": erp_server(run / "erp.sqlite"), "bank": bank_server(client / "bank"),
                        "mailbox": mailbox_server(run / "mail", run / "outbox")}

    async def start(self, days: list[str], dunning_day: str, respond) -> None:
        async with ToolBelt(self.servers, self.tracer, "console") as belt:
            cash = CashApplication(belt, RuleReader(), self.tracer, self.ops, self.s, "agent")
            coll = Collections(belt, RuleReader(), self.tracer, self.ops, self.s, "agent", "agent")
            i = days.index(dunning_day)
            await cash.run(days[: i + 1])
            await coll.dunning_run(dunning_day)
            respond([{"letter_id": k, "kunnr": v["kunnr"], "docs": v["docs"]} for k, v in coll.letters.items()])
            for d in days[i + 1:]:
                await cash.run([d])
                await coll.replies(d)

    async def accept(self, subject: str, by: str) -> dict:
        item = next((q for q in self.ops.queue("cash_application", "agent") if q["subject"] == subject), None)
        if not item:
            raise KeyError(subject)
        if not item["proposal"]:
            raise ValueError("this item has no proposal to accept; post it in the ERP by hand")
        async with ToolBelt(self.servers, self.tracer, by) as belt:
            res = await belt.call("erp", "post_clearing", payment_id=subject, lines=item["proposal"],
                                  idempotency_key=f"{subject}:review", posted_by=f"person/{by}", posted_on=item["day"])
        if "rejected" in res:
            raise ValueError(res["rejected"])
        self.ops.resolve("cash_application", "agent", subject, f"accepted by {by}")
        return res

    def reject(self, subject: str, by: str) -> None:
        self.ops.resolve("cash_application", "agent", subject, f"rejected by {by}")


def build_demo(run: Path, quick: bool = True) -> Engagement:
    import yaml

    from cofa.world.client import build, load, respond
    cfg = load(ROOT / "config/world.yaml")
    if quick:
        cfg = {**cfg, "customers": 30, "bank_days": 12, "collections": {**cfg["collections"], "dunning_day": 8}}
    shutil.rmtree(run, ignore_errors=True)
    build(cfg, run / "world")
    (run / "state").mkdir(parents=True)
    shutil.copy(run / "world" / "client" / "erp.sqlite", run / "state" / "erp.sqlite")
    shutil.copytree(run / "world" / "client" / "mail", run / "state" / "mail")
    settings = yaml.safe_load((ROOT / "config/product.yaml").read_text())
    days = Bank(run / "world" / "client" / "bank").days()                     # the calendar comes from the bank
    dunning = days[min(settings["collections"]["dunning_bank_day"], len(days) - 4) - 1]
    e = Engagement(run / "world" / "client", run / "state", settings)
    asyncio.run(e.start(days, dunning, lambda letters: respond(cfg, run / "world", run / "state" / "mail", letters)))
    return e


def create_app(engagement: Engagement, reports: Path = ROOT / "reports") -> FastAPI:
    app = FastAPI(title="cfo-office-agents console")
    app.state.e = engagement

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/summary")
    def summary():
        out = {}
        for name in ("dev", "heldout"):
            p = reports / f"{name}.json"
            if p.exists():
                r = json.loads(p.read_text())
                out[name] = {"company": r["company"], "period": r["period"], "planted": r["planted"], "readers": r["readers"],
                             "business_case": r["business_case"], "reuse": r["reuse"], "gate": r.get("gate", []),
                             "runs": {k: {"cash": {x: y for x, y in v["cash"].items() if x != "by_kind"},
                                          "collections": {x: y for x, y in v["collections"].items() if x != "by_situation"},
                                          "traces": v["traces"]} for k, v in r["runs"].items()}}
        return out

    @app.get("/api/review")
    def review():
        return {"items": app.state.e.ops.queue("cash_application", "agent")}

    @app.post("/api/review/{subject}/accept")
    async def accept(subject: str, by: str = "clerk"):
        try:
            return await app.state.e.accept(subject, by)
        except KeyError:
            raise HTTPException(404, "no open review item with this id") from None
        except ValueError as err:
            raise HTTPException(409, str(err)) from None

    @app.post("/api/review/{subject}/reject")
    def reject(subject: str, by: str = "clerk"):
        app.state.e.reject(subject, by)
        return {"rejected": subject}

    @app.get("/api/collections")
    def collections():
        rows = [d for d in app.state.e.ops.decisions("collections", "agent") if not d["subject"].startswith("dunning-")]
        drafts = []
        for p in sorted((app.state.e.run / "outbox").glob("*.txt")):
            head = dict(ln.split(": ", 1) for ln in p.read_text().split("\n\n", 1)[0].splitlines() if ": " in ln)
            drafts.append({"name": p.name, "in_reply_to": head.get("In-Reply-To", "")})
        return {"replies": rows, "drafts": drafts}

    @app.get("/api/drafts/{name}")
    def draft(name: str):
        p = app.state.e.run / "outbox" / name
        if not p.exists() or p.parent != app.state.e.run / "outbox":
            raise HTTPException(404, "no such draft")
        return {"name": name, "text": p.read_text()}

    @app.get("/api/traces/{subject}")
    def traces(subject: str):
        recs = app.state.e.tracer.records()
        roots = [r for r in recs if r["attrs"].get("entry") == subject or r["attrs"].get("mail") == subject]
        ids = {r["trace"] for r in roots}
        return {"spans": [r for r in recs if r["trace"] in ids]}

    dist = ROOT / "web" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")
    return app


if __name__ == "__main__":
    import uvicorn
    run = Path(os.environ.get("COFA_RUN", ROOT / "work" / "console"))
    eng = build_demo(run, quick=os.environ.get("COFA_FULL") != "1")
    uvicorn.run(create_app(eng), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
