# Working in cfo-office-agents

Fast feedback first: `python -m pytest -q` builds a small client (30 customers, 12 bank days) and checks the world,
the ERP connector, MCP tools, readers, guard, both engagements, the invariants and the API in about ten seconds.
`cd web && npm test` for the console. `ruff check .` for lint. After any change to the world, the platform, an
engagement or the settings, run

```bash
python -m cofa.eval.cli evaluate && python -m cofa.eval.cli gate && python -m cofa.eval.cli readme
```

(about 25 seconds) and commit `reports/dev.json` and `README.md`. CI fails when they disagree, and re-runs the
month to check that the dev numbers reproduce.

## Layout

| path | what it is | may read |
|---|---|---|
| `cofa/world` | the client: customers, invoices, bank files, mailbox, customers' replies to letters, and the truth | `config/world.yaml` or `config/heldout.yaml`, `cofa/keyed.py` |
| `cofa/platform` | MCP servers (`erp`, `bank`, `mailbox`), ERP connector, readers (rules, Claude), guard, tracing, ops store | the client's systems |
| `cofa/engagements` | cash application and collections | MCP tools only, through `ToolBelt` |
| `cofa/eval` | runs the designs on copies of the client, scores against the truth, gate, README | everything |
| `cofa/service` | the console's API: runs the platform on a client, lets a person work the review queue | the platform |
| `web` | the console: `src/features/*` per view, `src/shared/theme.ts` for every colour, size and duration | the API |

## Invariants (checked in `tests/test_invariants.py` and the tests)

1. **The truth stays in the world.** Nothing in `cofa/platform`, `cofa/engagements` or `cofa/service` imports
   `cofa.world` or reads `truth/`. Only `cofa/eval` compares with it.
2. **The world does not read the platform's settings.** `cofa/world` never reads `config/product.yaml`,
   `config/gate.yaml` or the platform. Customers react to the letters they receive (`respond`), nothing else.
3. **Same luck for every design.** Every draw is keyed (`cofa/keyed.py`); every design gets its own copy of the same
   ERP and mailbox.
4. **The model reads and code decides.** A reader returns fields. Posting, blocking and drafting are decided by
   code that checks every cent against the ERP.
5. **Customer text is data.** The guard splits off anything addressed to an AI before a reader sees it; such text is
   reported and never used as a fact.
6. **Identifiers decide, names propose.** An IBAN in the master data, an invoice number with its exact amount, or a
   PO number with its exact amount can decide. A customer name only ever proposes.
7. **Every ERP write once.** A posting carries an idempotency key and is atomic; nothing is posted beyond what is
   open. Replies are drafts; nothing is sent.
8. **Engagements reach the client only through MCP.** No engagement opens a database or a file of the client.
9. **Settings in config. Generated reports.** Every number in the README comes from `reports/`.

## The held-out rule

`config/heldout.yaml` (a second client with advice layouts, reply phrasings and payment patterns dev never showed)
is run once with `python -m cofa.eval.cli heldout`, with the code and settings dev ended on. It writes
`config/heldout.lock` and `reports/heldout.json`; findings go into `docs/heldout.md`. Fixes are made and measured
on dev. The held-out client is not run again and `config/gate.yaml` is not moved.
