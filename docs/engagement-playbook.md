# Adding an engagement

Collections was built as the second engagement to test whether the platform is real: what did it need that cash
application had not already built? The answer is in `reports/dev.json` under `reuse`. A third engagement (for
example, dispute resolution or payment-term negotiation) follows the same steps.

1. **Name the status quo.** Write down what the client does today, as a design that runs on the same data. The
   standard dunning run was the status quo for collections. Every claim is a difference against it.
2. **Find the client systems it touches** and check that the MCP servers expose them. Collections needed two new
   ERP tools (`record_dunning`, `block_dunning`) and one new mailbox tool (`draft_reply`). Nothing else changed in
   the platform.
3. **Decide what the model reads and what code decides.** In collections, the model reads a reply into an intent,
   documents, a date and a reason. Code decides: a promise blocks until that date; "already paid" is searched in the
   bank, and only an unapplied payment for the right amount counts.
4. **Write every decision with its evidence** (`Ops.decide`). What a person must decide goes to the review queue
   with a proposal.
5. **Plant the cases in the world before scoring them.** The world's customers react to what the engagement does
   (`respond`), so letters sent to the wrong customers produce the replies they would.
6. **Write gate lines before the held-out client runs.**
