"""python -m cofa.eval.cli evaluate [--quick] | gate | heldout | readme [--check]"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from cofa.eval import gate
from cofa.eval.run import ROOT, evaluate, write_report


def brief(rep: dict) -> None:
    for k, r in rep.get("runs", {}).items():
        c, m = r["cash"], r["collections"]
        print(f"{k:14} cash: right {c['posted_right_share']:.3f} wrong {c['posted_wrong']} ({c['posted_wrong_eur']} EUR) "
              f"review {c['review_share']:.3f}  collections: letters to payers {m['letters_to_customers_who_had_paid']}, "
              f"replies right {m['replies_handled_right']}/{m['replies']}")
    for ln in rep.get("gate", []):
        print(("PASS " if ln["pass"] else "FAIL ") + f"{ln['name']}: {ln['value']} {ln['op']} {ln['target']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cofa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("--quick", action="store_true")
    e.add_argument("--keep", action="store_true", help="keep each run's ERP, ops store, mailbox and drafts under work/")
    sub.add_parser("gate")
    sub.add_parser("heldout")
    r = sub.add_parser("readme")
    r.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "evaluate":
        rep = evaluate(quick=args.quick, keep=args.keep)
        rep["gate"] = gate.check(rep, ROOT / "config/gate.yaml")
        write_report(rep, "quick" if args.quick else "dev")
        brief(rep)
        return 0
    if args.cmd == "gate":
        rep = json.loads((ROOT / "reports/dev.json").read_text())
        lines = gate.check(rep, ROOT / "config/gate.yaml")
        if rep.get("gate") != lines:
            rep["gate"] = lines
            write_report(rep, "dev")
        brief({"gate": lines})
        return 0 if all(x["pass"] for x in lines) else 1
    if args.cmd == "heldout":
        lock = ROOT / "config/heldout.lock"
        if lock.exists():
            print(f"the held-out client was run once already ({lock.read_text().strip()}); it is not run again")
            return 1
        rep = evaluate("config/heldout.yaml")
        rep["gate"] = gate.check(rep, ROOT / "config/gate.yaml")
        write_report(rep, "heldout")
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        lock.write_text(f"run once at commit {commit or 'unknown'}\n")
        brief(rep)
        return 0
    if args.cmd == "readme":
        from cofa.eval import readme
        text, path = readme.render(), ROOT / "README.md"
        if args.check:
            if not path.exists() or path.read_text() != text:
                print("README.md does not match the reports: run python -m cofa.eval.cli readme")
                return 1
            return 0
        path.write_text(text)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
