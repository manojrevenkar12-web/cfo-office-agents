# SKILLS.md

## Start a new engagement on the platform

Follow docs/engagement-playbook.md: a module in `cofa/engagements` that takes a `ToolBelt`, a reader, a tracer and
the ops store; client access only through MCP tools; every decision written with `Ops.decide` and its evidence; a
design that is the client's status quo to compare with; a scorer in `cofa/eval/score.py`; gate lines before the
held-out run.

## Connect a new client system

Add an MCP server in `cofa/platform/mcp_servers.py` with tools that read, and tools that write idempotently (a key
per write, atomic, refusing what does not fit). Describe each tool for a model, since Claude Code and Claude Desktop
can use the same servers over stdio. Add it to `servers()` and to `run_design` in `cofa/eval/run.py`.

## Teach the reader a new layout or phrasing

Add the case to the world first (`cofa/world/texts.py`, behind a config switch), then a parametrised case in
`tests/test_platform.py`, then the rule reader. The Claude reader needs no change unless the schema does. Measure
with `readers` in `reports/dev.json`.

## Read with Claude

Set `ANTHROPIC_API_KEY` and `reader: claude` in `config/product.yaml`. Each read is a span with its tokens; the
README's trace line then shows tokens per decision.

## Use the client's systems from Claude Code

`python -m cofa.platform.mcp_servers erp --client <dir>/client --ops <dir>/ops` (and `bank`, `mailbox`) as stdio
MCP servers in `.mcp.json`. The mailbox server only drafts.
