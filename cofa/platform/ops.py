"""The platform's own store, separate from the client's systems: every decision with its evidence, the review
queue a person works through, and the drafts waiting to be sent."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
create table if not exists decisions (id integer primary key, engagement text not null, design text not null,
    subject text not null, day text not null, action text not null, kunnr text, reason text not null,
    proposal text, evidence text, unique (engagement, design, subject, day));
create table if not exists review (subject text not null, engagement text not null, design text not null, day text not null,
    kunnr text, amount_cents integer, reason text not null, proposal text, evidence text,
    status text not null default 'open', resolved_by text, primary key (engagement, design, subject));
"""


class Ops:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as c:
            c.executescript(SCHEMA)

    def _c(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def decide(self, engagement: str, design: str, subject: str, day: str, action: str, reason: str,
               kunnr: str | None = None, proposal=None, evidence=None, amount_cents: int | None = None) -> None:
        with closing(self._c()) as c:
            c.execute("insert or replace into decisions (engagement, design, subject, day, action, kunnr, reason, proposal, evidence) "
                      "values (?,?,?,?,?,?,?,?,?)", (engagement, design, subject, day, action, kunnr, reason,
                                                     json.dumps(proposal or []), json.dumps(evidence or [])))
            if action == "review":
                c.execute("insert or replace into review (subject, engagement, design, day, kunnr, amount_cents, reason, proposal, evidence) "
                          "values (?,?,?,?,?,?,?,?,?)", (subject, engagement, design, day, kunnr, amount_cents, reason,
                                                         json.dumps(proposal or []), json.dumps(evidence or [])))
            elif action == "post":
                c.execute("update review set status = 'resolved', resolved_by = 'agent' where engagement = ? and design = ? and subject = ?",
                          (engagement, design, subject))
            c.commit()

    def queue(self, engagement: str, design: str, status: str = "open") -> list[dict]:
        with closing(self._c()) as c:
            rows = c.execute("select * from review where engagement = ? and design = ? and status = ? order by day, subject",
                             (engagement, design, status)).fetchall()
        return [{**dict(r), "proposal": json.loads(r["proposal"] or "[]"), "evidence": json.loads(r["evidence"] or "[]")} for r in rows]

    def resolve(self, engagement: str, design: str, subject: str, by: str) -> None:
        with closing(self._c()) as c:
            c.execute("update review set status = 'resolved', resolved_by = ? where engagement = ? and design = ? and subject = ?",
                      (by, engagement, design, subject))
            c.commit()

    def decisions(self, engagement: str, design: str) -> list[dict]:
        with closing(self._c()) as c:
            rows = c.execute("select * from decisions where engagement = ? and design = ? order by id", (engagement, design)).fetchall()
        return [{**dict(r), "proposal": json.loads(r["proposal"] or "[]"), "evidence": json.loads(r["evidence"] or "[]")} for r in rows]
