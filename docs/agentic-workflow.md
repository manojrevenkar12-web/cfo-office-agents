# How this was built with a coding agent

The repository was written with Claude Code, with a person deciding what to build and checking the numbers.

- **The client first.** The ERP, bank files and mailbox, with the payment patterns a real accounts-receivable team
  sees, came before any agent code. Their mix was written down in `config/world.yaml` before the first result.
- **A status quo and a careless design to beat.** The ERP's standard matching is the baseline, and "model decides" is
  the design the platform's rules exist to prevent. Every rule in `cash_application.py` is there because one of the
  payment kinds in the README table needed it.
- **The agent's own mistakes, caught by the evaluation.** These came before the numbers were recorded:
  - the advice detector missed "Zahlungsavis" because it looked for a whole word;
  - a reference to an invoice that was already cleared went to review without a proposal, when it is a second
    payment;
  - "already paid" counted a bank payment that had been applied to other invoices.
  Each was found as a row in the payment-kind table that did not add up, fixed, and re-measured on dev.
- **Customers react to what the engagement does.** An early version of the world wrote every customer's reply
  whether a letter went out or not. Scoring then counted replies to letters that were never sent. Replies now come
  from `respond`, called with the letters actually sent.
- **The held-out client was written before it was run, and run once.**
