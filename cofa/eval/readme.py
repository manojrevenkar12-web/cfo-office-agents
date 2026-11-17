"""README from the reports: every number in it comes from reports/dev.json or reports/heldout.json."""
from __future__ import annotations

import json

from cofa.eval.run import ROOT

RUN = {"status_quo": "the ERP's standard matching and dunning run", "model_decides": "a model that decides and posts",
       "platform": "**the platform's agents** (the model reads, code decides)"}
KINDS = {"exact_single": "one invoice number, exact amount", "multi_reference": "several invoice numbers in the reference",
         "remittance_advice": "the lines come in a payment advice by mail", "skonto": "cash discount taken in time",
         "late_skonto": "cash discount taken too late", "short_payment": "a deduction with a reason in the advice",
         "typo_reference": "a digit wrong or swapped in the invoice number", "po_reference_only": "only the customer's PO number",
         "no_reference": "no reference at all", "parent_payer": "the group's parent pays for a subsidiary",
         "duplicate": "first payment of an invoice paid twice", "duplicate_second": "second payment of the same invoice",
         "new_iban_name_variant": "a new IBAN and a spelling of the name we do not know"}


def pct(x, d=1):
    return "–" if x is None else f"{100 * x:.{d}f}%"


def eur(x):
    return f"€{x:,.0f}"


def show(line):
    v = line["value"]
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, float) and v <= 1 and ("share" in line["metric"]):
        return pct(v)
    return f"{v}"


def render() -> str:
    dev = json.loads((ROOT / "reports/dev.json").read_text())
    hp = ROOT / "reports/heldout.json"
    held = json.loads(hp.read_text()) if hp.exists() else None
    R, H = dev["runs"], (held or {}).get("runs", {})
    pl, b = dev["planted"], dev["business_case"]
    rows = []
    for k in ("status_quo", "model_decides", "platform"):
        c, m = R[k]["cash"], R[k]["collections"]
        h = H.get(k)
        rows.append(f"| {RUN[k]} | {pct(c['posted_right_share'])} | {c['posted_wrong']} ({eur(c['posted_wrong_eur'])}) | "
                    f"{c['injections_followed']} of {c['injections']} | {m['letters_to_customers_who_had_paid']} of {m['letters']} | "
                    f"{(c['clerk_minutes'] + m['clerk_minutes']) / 60:.1f} h | "
                    + (f"{pct(h['cash']['posted_right_share'])}, {h['cash']['posted_wrong']} wrong |" if h else "– |"))
    kinds = []
    for kind, label in KINDS.items():
        n = pl["kinds"].get(kind, 0)
        if not n:
            continue
        cells = []
        for k in ("status_quo", "model_decides", "platform"):
            o = R[k]["cash"]["by_kind"].get(kind, {})
            cells.append(f"{o.get('posted_right', 0)} / {o.get('posted_wrong', 0)}")
        kinds.append(f"| {label} | {n} | " + " | ".join(cells) + " |")
    cm = R["platform"]["collections"]
    sq = R["status_quo"]["collections"]
    rd = dev["readers"]
    tr = R["platform"]["traces"]
    gate_rows = []
    hg = {x["name"]: x for x in (held or {}).get("gate", [])}
    for ln in dev["gate"]:
        h = hg.get(ln["name"])
        gate_rows.append(f"| {ln['name']} | {show(ln)} {'✅' if ln['pass'] else '❌'} | "
                         + (f"{show(h)} {'✅' if h['pass'] else '❌'} |" if h else "– |"))
    passed = sum(x["pass"] for x in dev["gate"])
    if held:
        hpass = sum(x["pass"] for x in held["gate"])
        hr = held["readers"]
        held_text = (f"The held-out client (`config/heldout.yaml`, {held['company']}) was written before it was run, and run once "
                     f"with the code dev ended on. It brought advice layouts, reply phrasings and payment patterns the platform "
                     f"was not built on. It passed {hpass} of {len(held['gate'])} gate lines. The reader got "
                     f"{pct(hr['advice_exact_share'])} of advices and {pct(hr['reply_intent_share'])} of reply intents right, against "
                     f"{pct(rd['advice_exact_share'])} and {pct(rd['reply_intent_share'])} on dev. "
                     f"[docs/heldout.md](docs/heldout.md) says what failed, why, and what changes.")
    else:
        held_text = "The held-out client has not been run yet."
    return f"""# cfo-office-agents

**Claude agents deployed into a DACH company's finance stack over MCP: cash application from bank statements and
German remittance advice, then collections, on one shared platform with evals and tracing from day one.**

A German mid-market company receives a few hundred customer payments a month. Each one has to be matched to the
invoices it pays. The standard matching in the ERP clears the easy ones. A person does the rest from a 140-character
reference, a payment advice in somebody's mailbox and a guess about who paid. Meanwhile the dunning run sends
reminders for money that has already arrived. This repository is what a forward-deployed team would build into
such a client in a few weeks:

- **MCP servers into the client's systems**: `erp` (customer master, open items, idempotent postings, dunning),
  `bank` (ISO 20022 camt.054 credit notifications) and `mailbox` (advices and replies; drafts only, nothing is sent).
  The agents reach the client only through them, and so can Claude Code or Claude Desktop over stdio.
- **Engagement 1, cash application**: reads references and payment advices, explains every cent (open amount,
  Skonto within its period, deduction with a reason, credit notes), and posts. If it cannot, it sends the payment
  to a person with a proposal and the evidence.
- **Engagement 2, collections**, built on the same platform: no dunning letter for money that is in the review
  queue. Replies are read and acted on: a promise pauses dunning until its date, a dispute blocks the item with its
  reason, and "already paid" is checked against the bank first. Every answer is a draft in the customer's language.
- **The platform**: a reader interface (Claude with a strict tool schema, or an offline rule reader for air-gapped
  clients and CI), a guard that splits off text addressed to an AI, OpenTelemetry spans for every decision and tool
  call, a review queue, and evals against labelled truth.
- **A console** for the accounts-receivable clerk: the month's results, the review queue with proposal, evidence
  and the agent's trace, and the replies with their drafts (React, Framer Motion).

![The review queue: why a payment needs a person, the evidence, the proposal, and what the agent did](docs/img/review.png)

## Results on one month

The client is simulated (`cofa/world`): {pl['customers']} customers (some paid for by their group's parent),
{pl['invoices']:,} invoices and {pl['credit_notes']} credit notes, and {pl['payments']} payments over {pl['bank_days']} bank days with
{pl['advice_mails']} payment advices in four layouts. {pl['injections']} advices carry text telling an AI to put the money on someone
else's invoice. Every design runs on its own copy of the same ERP, bank files and mailbox.

| design | payments posted right, no person | posted wrong | AI instructions followed | dunning letters to customers whose money had arrived | clerk time | held-out client |
|---|---|---|---|---|---|---|
{chr(10).join(rows)}

- **Clerk time** counts {dev_minutes()}.
- **Business case**: {b['clerk_hours_saved_per_month']} clerk hours a month saved for this client, about
  {eur(b['eur_saved_per_year'])} a year at €48 an hour. That figure leaves out what the wrong postings and the
  {b['letters_to_paying_customers_avoided']} reminders to paying customers would cost.
- **Every review came with a proposal**: {pct(R['platform']['cash']['right_proposal_share_of_review'])} of the payments the platform
  sent to a person had the right proposal ready to accept.
- **Deductions**: {R['platform']['cash']['deductions_flagged_with_reason']} of {R['platform']['cash']['deductions']} were posted with the
  rest left open and blocked from dunning with its reason (price, damage, quantity).

**Where each design gets it right / wrong**, by what the payment looks like:

| payment | n | ERP standard | model decides | platform |
|---|---|---|---|---|
{chr(10).join(kinds)}

**Collections**:
- **The platform**: it sent {cm['letters']} letters, {cm['letters_to_customers_who_had_paid']} to a customer whose money had arrived. It
  handled {cm['replies_handled_right']} of {cm['replies']} replies right: promises recorded with their date, disputes
  blocked with the right reason, invoice copies drafted, and "already paid" checked against the bank.
- **The standard run**: it sent {sq['letters']} letters, {sq['letters_to_customers_who_had_paid']} of them to customers who had paid, and
  every one of its {sq['replies']} replies went to a person.

**Evals and observability**:
- **The reader alone**: {pct(rd['advice_exact_share'])} of {rd['advices']} advices read exactly (every line, amount and
  deduction) and {pct(rd['reply_intent_share'])} of {rd['replies']} reply intents. {rd['injections_flagged_and_ignored']} of
  {rd['injections']} AI-addressed passages were flagged and never used as facts.
- **Traces**: a payment decision takes {tr['cash']['median_ms']:.1f} ms median and {tr['cash']['tool_calls_per_decision']} MCP tool
  calls on average (the offline reader uses no tokens; with Claude each read's tokens are on its span).
- **Reuse**: collections is {dev['reuse']['collections_loc']} lines on a {dev['reuse']['platform_loc']}-line platform; only
  {pct(dev['reuse']['collections_new_share'], 0)} of what it runs is new.

## Held-out client

{held_text}

## Gate

Written after the first dev results and before the held-out client was run (`config/gate.yaml`).

| line | dev | held-out |
|---|---|---|
{chr(10).join(gate_rows)}

Dev passes {passed} of {len(dev['gate'])}.

## Limits

- **The client is simulated.** Its ERP is a reduced SAP FI-AR in SQLite, and its customers' writing comes from
  templates. The held-out client exists to show how far that carries.
- **The numbers come from the offline rule reader.** There was no model API key where this was built. The Claude
  reader has the same interface, a strict tool schema and tests against a stub client. Its accuracy, cost and latency
  on these mails are not measured here.
- **"Model decides" is an emulation** of a model trusted with the posting decision: it follows what the text says.
  It shows the failure modes the platform's rules exist for; it is not a measurement of any particular model.

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                         # world, platform, engagements, invariants and the API, about 10 s
python -m cofa.eval.cli evaluate            # the month for all three designs, about 25 s; writes reports/dev.json
cd web && npm ci && npm test && npm run build && cd ..
python -m cofa.service.api                  # console and API on :8080 (a quick client; COFA_FULL=1 for the month)
python -m cofa.platform.mcp_servers erp --client <client>/client --ops <ops>   # an MCP server over stdio
docker compose up                           # the same, in a container
```

- `cofa/world`: the client (ERP, bank, mailbox) and the truth. Nothing else reads the truth.
- `cofa/platform`: MCP servers, ERP connector, readers, guard, tracing, ops store.
- `cofa/engagements`: cash application and collections.
- `cofa/eval`: designs, scoring, gate and this README.
- `cofa/service`: the console's API.
- `web`: the console, feature-first, with theme tokens, Framer Motion, and loading, error and empty states.

[docs/engagement-playbook.md](docs/engagement-playbook.md) is how a third engagement is added, and
[docs/agentic-workflow.md](docs/agentic-workflow.md) is how this was built with Claude Code.
"""


def dev_minutes() -> str:
    import yaml
    m = yaml.safe_load((ROOT / "config/product.yaml").read_text())["review_minutes"]
    return (f"{m['accept_proposal']} minutes to accept a right proposal, {m['investigate']} to work a payment without one, "
            f"{m['undo_wrong_posting']} to find and undo a wrong posting, {m['reply_triage']} per reply a person reads and "
            f"{m['send_draft']} to check and send a draft (`config/product.yaml`)")
