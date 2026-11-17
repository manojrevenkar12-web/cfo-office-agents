# The held-out client

`config/heldout.yaml` (H1, Hofer Haustechnik Großhandel GmbH, Linz) was written before any held-out run. It was
run with the code dev ended on. The numbers are from `reports/heldout.json`: 150 customers, 521 payments, 117
payment advices, 22 bank days.

**Two attempts, one change.** The first attempt, at commit `7cc40d5`, stopped with an exception. A payment advice in
a layout the rule reader did not know was read into no lines, and the agent assumed there was at least one. It
produced no results. The only change before the second attempt (`ee3ae4f`) sends such a payment to a person.
Dev results were checked unchanged. Both attempts are recorded in `config/heldout.lock`. Afterwards, the platform
design was replayed once on a copy of the client to find the cause of finding 5. No number here comes from that
replay. The client is not run again.

## What it changed

- Two advice layouts dev never had:
  - a Swiss CSV export, with semicolons and `1'234.50`;
  - English prose that names the invoices but gives no amount per invoice.
- Replies to dunning letters phrased differently: "Reklamation", "mit unserem nächsten Zahllauf", "Der Ausgleich
  erfolgte bereits".
- More groups whose parent pays, more payments without a reference, more typos.
- Advices up to two bank days after the money.
- Cash discount at 3% in 14 days instead of 2% in 10.

## What came out

It passed 3 of 11 gate lines.

| | dev | held-out |
|---|---|---|
| posted right with no person | 96.1% | 84.3% |
| posted wrong | 0 | **0** |
| AI instructions followed | 0 of 9 | **0 of 11** |
| reviews with the right proposal | 100% | 28% |
| advices read exactly (reader alone) | 100% | 62.4% |
| reply intents right (reader alone) | 100% | 49.5% |
| dunning letters to customers whose money had arrived | 1 of 110 | 11 of 79 (status quo: 97 of 135) |
| replies handled right | 46 of 47 | 21 of 48 |
| clerk time against the status quo | 5.6% | 25.7% |

## What it showed

1. **The safety held; the coverage did not.** On unseen layouts and phrasing, every payment the platform could not
   explain went to a person: no wrong posting, no followed instruction. "Model decides" posted 111 payments wrong
   (€573,773) on the same client. Unknown text costs clerk time, not money, which is the order of failure the
   design is for.
2. **The rule reader is the weak part, as expected.** It read 62% of advices and 49% of reply intents. All the
   misses are in the new layouts and the new phrasing. This is what the Claude reader is for. With no model access
   where this was built, its accuracy on these mails is not measured. That is the first thing to measure with a key.
3. **The English prose advices need no model to fix.** They name the invoices but give no amounts. The engagement
   could treat them like invoice numbers in a reference: open amount, or open amount less discount, to the cent.
   It currently drops them because the reader returns lines without amounts.
4. **Letters to paying customers went from 1 to 11.** Two causes:
   - payments still waiting for an advice that comes two days late were not yet in the review queue on dunning day;
   - unreadable advices from a group's parent named the parent, not the subsidiaries that got the letters.
   Dunning should hold every customer with money that is waiting or in review, including the customers a payer pays
   for.
5. **"Already paid" was not found in 5 replies where the customer was right.** The search looks for one unapplied
   payment of the letter's amount from the customer's own IBANs. One of the five came from the group's parent. The
   other four did not match on amount or had been applied elsewhere. A person has to look at the payment that is
   there.
6. **The business case held, barely.** 22.2 clerk hours a month saved, against 24.6 on dev. The 25% line failed at
   25.7%.

## What to change, measured on dev

- Read the Swiss CSV layout (split on the record, not on `;`), and treat advices without amounts as invoice
  references.
- Run the Claude reader on the reply phrasings and measure it against the rule reader. Keep the rule reader as the
  offline fallback.
- Hold dunning for customers with waiting payments and for the customers a payer pays for.
- Search "already paid" across the group's IBANs, and show a person the customer's payments around the date instead
  of answering "no payment found".

Each change needs dev cases first: add the layouts and phrasings to the dev world behind its config, then measure.
None of these is done yet. `config/gate.yaml` was not moved.
